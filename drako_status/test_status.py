"""Unit tests for drako_status/status.py (scratch temp dirs only)."""
import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load():
    spec = importlib.util.spec_from_file_location(
        "drako_status_status_unit", HERE / "status.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


status = load()

KEYS = {"run_id", "phase", "status", "native_invocations", "checks_passed",
        "trace_observed", "score_observed", "evidence_confirmed"}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.d = self.base / "DRAKO-run"
        self.d.mkdir()

    def put(self, name, value, raw=False):
        p = self.d / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(value if raw else json.dumps(value))

    def valid(self):
        self.put("state.json", {"phase": "published", "native_invocations": 2,
                                "trace_id": "t1", "score_id": "s1",
                                "comment_id": "c1", "token": "PRIVATE_TOKEN"})
        self.put("evaluation.json", {"run_id": "DRAKO-run", "checks_passed": True,
                                     "trace_observed": True,
                                     "score_observed": True,
                                     "note": "PRIVATE_NOTE"})
        self.put("trace-receipt.json", {"trace_observed": True, "trace_id": "t1"})
        self.put("score-receipt.json", {"score_observed": True, "value": True,
                                        "trace_id": "t1", "score_id": "s1"})
        self.put("evidence/evidence-post.json",
                 {"status": "confirmed", "comment_id": "c1"})

    def run_status(self):
        r = status.inspect_run(self.d)
        self.assertEqual(set(r), KEYS)
        return r


class PhaseTests(Base):
    def test_missing_state(self):
        r = self.run_status()
        self.assertEqual((r["phase"], r["status"]), ("missing", "NOT_RUN"))
        self.assertEqual(r["run_id"], "DRAKO-run")

    def test_missing_directory(self):
        r = status.inspect_run(self.base / "nope")
        self.assertEqual(r["status"], "NOT_RUN")
        self.assertEqual(r["run_id"], "nope")

    def test_prepared(self):
        self.put("state.json", {"phase": "prepared", "native_invocations": 0})
        r = self.run_status()
        self.assertEqual(r["status"], "NOT_RUN")
        self.assertEqual(r["native_invocations"], 0)

    def test_launch_started_never_infers_liveness(self):
        self.put("state.json", {"phase": "launch_started",
                                "native_invocations": 1, "pid": os.getpid()})
        r = self.run_status()
        self.assertEqual(r["status"], "NEEDS_RECONCILIATION")
        self.assertNotIn("pid", json.dumps(r))

    def test_executed(self):
        self.valid()
        self.put("state.json", {"phase": "executed", "native_invocations": 1})
        r = self.run_status()
        self.assertEqual(r["status"], "EXECUTED_PENDING_PUBLICATION")
        self.assertFalse(any(r[k] for k in ("checks_passed", "trace_observed",
                                            "score_observed",
                                            "evidence_confirmed")))

    def test_unknown_phase_not_echoed(self):
        self.put("state.json", {"phase": "SECRET_PHASE", "native_invocations": 1})
        r = self.run_status()
        self.assertEqual(r["status"], "INVALID_EVIDENCE")
        self.assertNotIn("SECRET_PHASE", json.dumps(r))

    def test_bad_invocations(self):
        for bad in (-1, True, 1.5, "1", None):
            self.put("state.json", {"phase": "executed", "native_invocations": bad})
            self.assertEqual(self.run_status()["status"], "INVALID_EVIDENCE", bad)

    def test_non_object_state(self):
        self.put("state.json", [1, 2])
        self.assertEqual(self.run_status()["status"], "INVALID_EVIDENCE")


class PublishedTests(Base):
    def test_pass_no_private_fields(self):
        self.valid()
        r = self.run_status()
        self.assertEqual(r["status"], "PASS")
        self.assertEqual(r["native_invocations"], 2)
        self.assertTrue(all(r[k] for k in ("checks_passed", "trace_observed",
                                           "score_observed",
                                           "evidence_confirmed")))
        dumped = json.dumps(r)
        self.assertNotIn("PRIVATE", dumped)

    def assertIncomplete(self, flag=None):
        r = self.run_status()
        self.assertEqual(r["status"], "INCOMPLETE_EVIDENCE")
        if flag:
            self.assertFalse(r[flag])
        return r

    def test_each_missing_file(self):
        for name, flag in (("evaluation.json", "checks_passed"),
                           ("trace-receipt.json", "trace_observed"),
                           ("score-receipt.json", "score_observed"),
                           ("evidence/evidence-post.json", "evidence_confirmed")):
            self.valid()
            (self.d / name).unlink()
            self.assertIncomplete(flag)

    def test_missing_evidence_dir(self):
        self.valid()
        (self.d / "evidence" / "evidence-post.json").unlink()
        (self.d / "evidence").rmdir()
        self.assertIncomplete("evidence_confirmed")

    def test_evaluation_run_id_mismatch(self):
        self.valid()
        self.put("evaluation.json", {"run_id": "other", "checks_passed": True,
                                     "trace_observed": True,
                                     "score_observed": True})
        r = self.assertIncomplete("checks_passed")
        self.assertFalse(r["trace_observed"])

    def test_truthy_but_not_true(self):
        self.valid()
        self.put("evaluation.json", {"run_id": "DRAKO-run", "checks_passed": 1,
                                     "trace_observed": True,
                                     "score_observed": True})
        self.assertIncomplete("checks_passed")

    def test_trace_id_mismatch(self):
        self.valid()
        self.put("trace-receipt.json", {"trace_observed": True, "trace_id": "x"})
        self.assertIncomplete("trace_observed")

    def test_score_value_false(self):
        self.valid()
        self.put("score-receipt.json", {"score_observed": True, "value": False,
                                        "trace_id": "t1", "score_id": "s1"})
        self.assertIncomplete("score_observed")

    def test_score_id_mismatch(self):
        self.valid()
        self.put("score-receipt.json", {"score_observed": True, "value": True,
                                        "trace_id": "t1", "score_id": "s2"})
        self.assertIncomplete("score_observed")

    def test_evidence_not_confirmed(self):
        self.valid()
        self.put("evidence/evidence-post.json",
                 {"status": "pending", "comment_id": "c1"})
        self.assertIncomplete("evidence_confirmed")

    def test_comment_id_mismatch(self):
        self.valid()
        self.put("evidence/evidence-post.json",
                 {"status": "confirmed", "comment_id": "c2"})
        self.assertIncomplete("evidence_confirmed")

    def test_state_missing_ids_never_pass(self):
        self.valid()
        self.put("state.json", {"phase": "published", "native_invocations": 1})
        self.put("trace-receipt.json", {"trace_observed": True})
        self.put("score-receipt.json", {"score_observed": True, "value": True})
        self.put("evidence/evidence-post.json", {"status": "confirmed"})
        r = self.assertIncomplete()
        self.assertFalse(r["trace_observed"] or r["score_observed"]
                         or r["evidence_confirmed"])


class InvalidTests(Base):
    def test_malformed_state_no_leak(self):
        self.put("state.json", "{oops LEAKY_SECRET", raw=True)
        r = self.run_status()
        self.assertEqual(r["status"], "INVALID_EVIDENCE")
        self.assertNotIn("LEAKY_SECRET", json.dumps(r))

    def test_malformed_receipt(self):
        self.valid()
        self.put("score-receipt.json", "not json SECRET", raw=True)
        r = self.run_status()
        self.assertEqual(r["status"], "INVALID_EVIDENCE")
        self.assertNotIn("SECRET", json.dumps(r))

    def test_symlinked_state(self):
        target = self.base / "outside.json"
        target.write_text(json.dumps({"phase": "prepared",
                                      "native_invocations": 0}))
        (self.d / "state.json").symlink_to(target)
        self.assertEqual(self.run_status()["status"], "INVALID_EVIDENCE")

    def test_symlinked_receipt(self):
        self.valid()
        target = self.base / "outside.json"
        target.write_text((self.d / "trace-receipt.json").read_text())
        (self.d / "trace-receipt.json").unlink()
        (self.d / "trace-receipt.json").symlink_to(target)
        self.assertEqual(self.run_status()["status"], "INVALID_EVIDENCE")

    def test_symlinked_evidence_parent(self):
        self.valid()
        real = self.base / "real_evidence"
        (self.d / "evidence").rename(real)
        (self.d / "evidence").symlink_to(real, target_is_directory=True)
        self.assertEqual(self.run_status()["status"], "INVALID_EVIDENCE")

    def test_symlinked_root(self):
        self.valid()
        link = self.base / "linked_run"
        link.symlink_to(self.d, target_is_directory=True)
        self.assertEqual(status.inspect_run(link)["status"], "INVALID_EVIDENCE")

    def test_state_is_directory(self):
        (self.d / "state.json").mkdir()
        self.assertEqual(self.run_status()["status"], "INVALID_EVIDENCE")


class SymlinkRootTrailingSeparatorTests(Base):
    """Regression: "link/" and "link//" must not follow a symlinked root."""

    SUFFIXES = ("/", "//", "///")

    def make_link(self):
        link = self.base / "linked_run"
        link.symlink_to(self.d, target_is_directory=True)
        return link

    def assertInvalidForSuffixes(self, link):
        for suffix in self.SUFFIXES:
            r = status.inspect_run(str(link) + suffix)
            self.assertEqual(set(r), KEYS)
            self.assertEqual(r["status"], "INVALID_EVIDENCE", suffix)
            self.assertEqual(r["phase"], "invalid", suffix)
            self.assertFalse(any(r[k] for k in ("checks_passed",
                                                "trace_observed",
                                                "score_observed",
                                                "evidence_confirmed")))
            self.assertIsNone(r["native_invocations"])

    def test_published_target_never_pass(self):
        self.valid()
        link = self.make_link()
        self.assertInvalidForSuffixes(link)
        self.assertNotIn("PRIVATE",
                         json.dumps(status.inspect_run(str(link) + "/")))

    def test_prepared_target_not_not_run(self):
        self.put("state.json", {"phase": "prepared", "native_invocations": 0})
        self.assertInvalidForSuffixes(self.make_link())

    def test_empty_target_not_not_run(self):
        # Target lacks state.json; without the fix this reads as NOT_RUN.
        self.assertInvalidForSuffixes(self.make_link())

    def test_pathlike_link_with_trailing_separator(self):
        self.valid()
        link = self.make_link()
        # Path objects drop trailing separators; still a symlink root.
        self.assertEqual(status.inspect_run(Path(str(link) + "/"))["status"],
                         "INVALID_EVIDENCE")

    def test_dangling_link_with_trailing_separator(self):
        link = self.base / "dangling"
        link.symlink_to(self.base / "does-not-exist", target_is_directory=True)
        for suffix in self.SUFFIXES:
            self.assertEqual(status.inspect_run(str(link) + suffix)["status"],
                             "INVALID_EVIDENCE", suffix)

    def test_cli_rejects_trailing_separator_link(self):
        self.valid()
        link = self.make_link()
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = status.main([str(link) + "//"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out.getvalue())["status"],
                         "INVALID_EVIDENCE")

    def test_real_directory_with_trailing_separators_still_works(self):
        self.valid()
        for suffix in self.SUFFIXES:
            r = status.inspect_run(str(self.d) + suffix)
            self.assertEqual(r["status"], "PASS", suffix)
            self.assertEqual(r["run_id"], "DRAKO-run", suffix)

    def test_missing_directory_with_trailing_separator(self):
        r = status.inspect_run(str(self.base / "nope") + "//")
        self.assertEqual((r["status"], r["run_id"]), ("NOT_RUN", "nope"))

    def test_symlinked_parent_of_real_run_unaffected_scope(self):
        # Only the root itself is checked; a non-symlink real run still passes.
        self.valid()
        self.assertEqual(status.inspect_run(str(self.d) + "/")["status"],
                         "PASS")


class CliTests(Base):
    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = status.main(list(args))
        return code, out.getvalue()

    def test_exit_codes(self):
        code, out = self.cli(str(self.d))
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["status"], "NOT_RUN")
        self.put("state.json", {"phase": "launch_started", "native_invocations": 1})
        self.assertEqual(self.cli(str(self.d))[0], 3)
        self.put("state.json", {"phase": "executed", "native_invocations": 1})
        self.assertEqual(self.cli(str(self.d))[0], 1)
        self.valid()
        code, out = self.cli(str(self.d))
        self.assertEqual(code, 0)
        self.assertEqual(set(json.loads(out)), KEYS)
        self.put("state.json", "{bad", raw=True)
        self.assertEqual(self.cli(str(self.d))[0], 1)

    def test_usage(self):
        self.assertEqual(self.cli()[0], 1)


if __name__ == "__main__":
    unittest.main()
