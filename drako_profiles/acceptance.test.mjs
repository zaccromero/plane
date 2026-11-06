import {test} from 'node:test';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
const {summariseProfile:s}=await import(pathToFileURL(process.env.DRAKO_TARGET_SOURCE).href);
for(const [name,input,want] of [['empty',[],[0,0]],['singleton',[12],[0,0]],['negative',[-20,-5,-10],[15,5]],['mixed',[100,110,106,112,100],[16,16]],['flat',[2,2,2],[0,0]],['descent',[20,12,0],[0,20]]]) test(name,()=>{const before=[...input];const v=s(input);assert.deepEqual(v,{gain_m:want[0],loss_m:want[1]});assert.deepEqual(input,before)});
for(const x of [NaN,Infinity,-Infinity]) for(const pos of ['single','first','middle','last']) test('reject '+String(x)+' '+pos,()=>{const input={single:[x],first:[x,1],middle:[1,x,2],last:[1,x]}[pos];assert.throws(()=>s(input),e=>e instanceof RangeError&&e.message.length>0)});
for(const input of [[-Number.MAX_VALUE,Number.MAX_VALUE],[Number.MAX_VALUE,-Number.MAX_VALUE],[0,Number.MAX_VALUE,0,Number.MAX_VALUE],[Number.MAX_VALUE,0,Number.MAX_VALUE,0],Array(2)]) test('reject arithmetic overflow or missing sample '+String(input),()=>assert.throws(()=>s(input),RangeError));
test('finite large values remain valid',()=>assert.deepEqual(s([0,Number.MAX_VALUE]),{gain_m:Number.MAX_VALUE,loss_m:0}));
