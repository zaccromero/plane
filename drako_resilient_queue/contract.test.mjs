import test from 'node:test';
import assert from 'node:assert/strict';
const {summariseProfile:s}=await import(process.env.DRAKO_TARGET_SOURCE);
test('getter-backed finite samples are read once with preserved gain/loss',()=>{
 for(const values of [[100,110,106],[-10,-5,-8],[0],[0,1e16,0,1,0,1,0],[]]){
  const expected=s(values);const counts=values.map(()=>0);let lengths=0;
  const input={get length(){assert.equal(++lengths,1);return values.length;}};
  values.forEach((value,i)=>Object.defineProperty(input,i,{get(){assert.equal(++counts[i],1,'sample '+i+' repeated');return value;}}));
  assert.deepEqual(s(input),expected);assert.deepEqual(counts,values.map(()=>1));
 }
});
