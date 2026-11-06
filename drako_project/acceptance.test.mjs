// Immutable independent acceptance. Target path is bound by the trusted runner.
import test from 'node:test';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
const {isAllowed,HARD_DENY_PORTS}=await import(pathToFileURL(process.env.DRAKO_TARGET_GUARD).href);
const url='http://localhost:3000/';
const malformed=[null,42,false,[],{allowedPorts:42},{allowedPorts:'3000'},{allowedPorts:{}},{allowedPorts:[3000,'3001']},{allowedPorts:[NaN]},{allowedPorts:[Infinity]},{allowedPorts:[0]},{allowedPorts:[65536]},{allowedPorts:[1.5]}];
for (let i=0;i<malformed.length;i++) test('malformed config fails closed without throwing '+i,()=>{
 let r;assert.doesNotThrow(()=>{r=isAllowed(url,malformed[i]);});
 assert.equal(r.allowed,false);assert.equal(typeof r.reason,'string');assert.ok(r.reason.length>0);
});
test('valid defaults and arrays/Sets retain behavior',()=>{
 assert.equal(isAllowed(url).allowed,true);
 assert.equal(isAllowed(url,{}).allowed,true);
 assert.equal(isAllowed(url,{allowedPorts:null}).allowed,true);
 assert.equal(isAllowed(url,{allowedPorts:[3000]}).allowed,true);
 assert.equal(isAllowed(url,{allowedPorts:new Set([3000])}).allowed,true);
 assert.equal(isAllowed(url,{allowedPorts:[]}).allowed,false);
});
test('hard-deny cannot be overridden',()=>{
 assert.ok(HARD_DENY_PORTS.length>=16);
 for(const port of HARD_DENY_PORTS)assert.equal(isAllowed('http://localhost:'+port+'/',{allowedPorts:[port,3000]}).allowed,false);
});
test('non-HTTP and remote targets stay denied',()=>{
 assert.equal(isAllowed('javascript:alert(1)',{allowedPorts:[3000]}).allowed,false);
 assert.equal(isAllowed('http://example.com:3000/',{allowedPorts:[3000]}).allowed,false);
});
