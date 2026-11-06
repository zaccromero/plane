// Trusted, profile-specific verifier; never evaluated from ticket/model text.
import fs from 'node:fs';
const {default:ts}=await import(process.argv[3]);
const source=fs.readFileSync(process.argv[2],'utf8');
const tree=ts.createSourceFile('profile.ts',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TS);
if(tree.parseDiagnostics.length)throw Error('Source parse failed');
if(tree.statements.length!==1||!ts.isFunctionDeclaration(tree.statements[0])||tree.statements[0].name?.text!=='summariseProfile')throw Error('Only the pure exported function is permitted');
function walk(n){
 if(ts.isImportDeclaration(n)||ts.isImportEqualsDeclaration(n)||ts.isExportDeclaration(n)||ts.isAwaitExpression(n)||ts.isTaggedTemplateExpression(n))throw Error('Outside pure function policy');
 if(ts.isCallExpression(n)&&!['Number.isFinite','String'].includes(n.expression.getText(tree)))throw Error('Only Number.isFinite and String calls permitted');
 if(ts.isNewExpression(n)&&n.expression.getText(tree)!=='RangeError')throw Error('Only RangeError construction permitted');
 if(ts.isPropertyAccessExpression(n)&&!['length','isFinite'].includes(n.name.text))throw Error('Outside pure property policy');
 if(ts.isIdentifier(n)&&['process','globalThis','global','eval','Function','require','module','exports','fetch','console','constructor','__proto__','prototype'].includes(n.text))throw Error('Forbidden runtime capability');
 ts.forEachChild(n,walk);
}
walk(tree);console.log('PURE_SOURCE_POLICY_PASS');
