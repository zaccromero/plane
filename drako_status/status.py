"""Evidence-aware, read-only inspection of a Drako run directory.

inspect_run(directory) returns a dict with exactly the keys in RESULT_KEYS.
It reads only the expected run JSON files, refuses symlinks inside the run
(and a symlinked run root, including one supplied with trailing path
separators such as "link/" or "link//") without following them, never echoes
arbitrary fields or raw parse errors, and never infers process liveness.

No network, subprocesses or mutations.
"""
import json
import os
import stat
import sys

RESULT_KEYS = (
    "run_id",
    "phase",
    "status",
    "native_invocations",
    "checks_passed",
    "trace_observed",
    "score_observed",
    "evidence_confirmed",
)

KNOWN_PHASES = ("prepared", "launch_started", "executed", "published")

STATE_FILE = ("state.json",)
EVALUATION_FILE = ("evaluation.json",)
TRACE_FILE = ("trace-receipt.json",)
SCORE_FILE = ("score-receipt.json",)
EVIDENCE_FILE = ("evidence", "evidence-post.json")

MAX_BYTES = 1024 * 1024

EXIT_CODES = {"PASS": 0, "NOT_RUN": 2, "NEEDS_RECONCILIATION": 3}

_MISSING = object()


class _Invalid(Exception):
    """Internal marker: evidence is unsafe or malformed. Carries no detail."""


def _run_id(directory):
    name = os.path.basename(os.path.normpath(os.fspath(directory)))
    return name


def _strip_trailing_separators(path):
    """Remove trailing separators so lstat sees the final component itself.

    lstat("link/") or lstat("link//") resolves the symlink because the
    trailing separator forces directory traversal; stripping them lets the
    root check observe the link. A path consisting only of separators is
    returned unchanged (it is the filesystem root, never a symlink).
    """
    seps = os.sep + (os.altsep or "")
    if isinstance(path, bytes):
        seps = os.fsencode(seps)
    stripped = path.rstrip(seps)
    return stripped if stripped else path


def _read_json(root, parts):
    """Read root/parts as a JSON object without following any symlink.

    Returns _MISSING when the file (or a parent inside root) does not exist.
    Raises _Invalid for symlinks, non-regular files, oversize or malformed
    content, or a non-object top-level value.
    """
    current = root
    for index, part in enumerate(parts):
        if isinstance(current, bytes):
            part = os.fsencode(part)
        current = os.path.join(current, part)
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            return _MISSING
        except OSError:
            raise _Invalid()
        if stat.S_ISLNK(info.st_mode):
            raise _Invalid()
        is_last = index == len(parts) - 1
        if not is_last and not stat.S_ISDIR(info.st_mode):
            raise _Invalid()
        if is_last and not stat.S_ISREG(info.st_mode):
            raise _Invalid()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(current, flags)
    except FileNotFoundError:
        return _MISSING
    except OSError:
        raise _Invalid()
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            raise _Invalid()
        chunks = []
        total = 0
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_BYTES:
                raise _Invalid()
            chunks.append(chunk)
    except OSError:
        raise _Invalid()
    finally:
        os.close(fd)
    try:
        value = json.loads(b"".join(chunks).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise _Invalid()
    if not isinstance(value, dict):
        raise _Invalid()
    return value


def _nonempty_str(value):
    return isinstance(value, str) and value != ""


def _result(run_id, phase, status, invocations=None, checks=False,
            trace=False, score=False, evidence=False):
    return {
        "run_id": run_id,
        "phase": phase,
        "status": status,
        "native_invocations": invocations,
        "checks_passed": checks is True,
        "trace_observed": trace is True,
        "score_observed": score is True,
        "evidence_confirmed": evidence is True,
    }


def _invalid(run_id):
    return _result(run_id, "invalid", "INVALID_EVIDENCE")


def inspect_run(directory):
    run_id = _run_id(directory)
    # Strip trailing separators before lstat: "link/" and "link//" would
    # otherwise resolve the symlink and hide it from the root check.
    root = _strip_trailing_separators(os.fspath(directory))
    try:
        root_info = os.lstat(root)
    except FileNotFoundError:
        return _result(run_id, "missing", "NOT_RUN")
    except OSError:
        return _invalid(run_id)
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        return _invalid(run_id)

    try:
        state = _read_json(root, STATE_FILE)
        if state is _MISSING:
            return _result(run_id, "missing", "NOT_RUN")

        phase = state.get("phase")
        if not isinstance(phase, str) or phase not in KNOWN_PHASES:
            return _invalid(run_id)

        invocations = state.get("native_invocations")
        if (not isinstance(invocations, int) or isinstance(invocations, bool)
                or invocations < 0):
            return _invalid(run_id)

        if phase == "prepared":
            return _result(run_id, phase, "NOT_RUN", invocations)
        if phase == "launch_started":
            return _result(run_id, phase, "NEEDS_RECONCILIATION", invocations)
        if phase == "executed":
            return _result(run_id, phase, "EXECUTED_PENDING_PUBLICATION",
                           invocations)

        # phase == "published": every claim must be backed by evidence.
        evaluation = _read_json(root, EVALUATION_FILE)
        trace_receipt = _read_json(root, TRACE_FILE)
        score_receipt = _read_json(root, SCORE_FILE)
        evidence_post = _read_json(root, EVIDENCE_FILE)
    except _Invalid:
        return _invalid(run_id)

    trace_id = state.get("trace_id")
    score_id = state.get("score_id")
    comment_id = state.get("comment_id")

    evaluation_ok = (
        evaluation is not _MISSING
        and _nonempty_str(run_id)
        and evaluation.get("run_id") == run_id
    )
    checks = evaluation_ok and evaluation.get("checks_passed") is True

    trace = (
        evaluation_ok
        and evaluation.get("trace_observed") is True
        and _nonempty_str(trace_id)
        and trace_receipt is not _MISSING
        and trace_receipt.get("trace_observed") is True
        and trace_receipt.get("trace_id") == trace_id
    )

    score = (
        evaluation_ok
        and evaluation.get("score_observed") is True
        and _nonempty_str(trace_id)
        and _nonempty_str(score_id)
        and score_receipt is not _MISSING
        and score_receipt.get("score_observed") is True
        and score_receipt.get("value") is True
        and score_receipt.get("trace_id") == trace_id
        and score_receipt.get("score_id") == score_id
    )

    evidence = (
        _nonempty_str(comment_id)
        and evidence_post is not _MISSING
        and evidence_post.get("status") == "confirmed"
        and evidence_post.get("comment_id") == comment_id
    )

    status = "PASS" if (checks and trace and score and evidence) else \
        "INCOMPLETE_EVIDENCE"
    return _result(run_id, phase, status, invocations, checks, trace, score,
                   evidence)


def exit_code(status):
    return EXIT_CODES.get(status, 1)


def main(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    if len(args) != 1:
        sys.stderr.write("usage: python status.py DIRECTORY\n")
        return 1
    result = inspect_run(args[0])
    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
    return exit_code(result["status"])


if __name__ == "__main__":
    sys.exit(main())
