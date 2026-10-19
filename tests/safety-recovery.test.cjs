const {test}=require('node:test');const assert=require('node:assert/strict');
const Model=require('../integration/omarchy/gabe.pitpat/Model.js');
test('fault ID blocks motion even if a stale UI snapshot says unblocked',()=>{
 const s={available:true,connected:true,blocked:false,stale:false,recovery:false,fault_id:'fault',metrics:{state:3,speed_raw:0}};
 assert.equal(Model.view(s,true).canStartPause,false);
 assert.equal(Model.view(s,true).canStop,true);
});
