import test from 'node:test';import assert from 'node:assert/strict';
const {summariseProfile:s}=await import(process.env.DRAKO_TARGET_SOURCE);
test('missing and null elevation input reject with descriptive RangeError',()=>{
 for(const value of [null,undefined])assert.throws(()=>s(value),e=>e instanceof RangeError&&e.message.length>0);
 assert.throws(()=>s(),e=>e instanceof RangeError&&e.message.length>0);
 for(const input of [[],Object.freeze([1]),new Float64Array([2,5,3])])assert.deepEqual(s(input),input.length<2?{gain_m:0,loss_m:0}:{gain_m:3,loss_m:2});
});
