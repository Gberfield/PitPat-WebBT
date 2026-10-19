const {test}=require('node:test');const assert=require('node:assert/strict');
const Model=require('../integration/omarchy/gabe.pitpat/Model.js');
const stopped={available:true,connected:true,blocked:false,stale:false,recovery:false,target_speed:1000,owner_present:true,owner_kind:'tray',
    metrics:{speed_raw:0,state:3,unit_mode:0,distance:1609,steps:1000,calories:30,duration:600000}};
test('native model gates motion by owner and fresh state but permits global Stop',()=>{
    for(const state of [0,1,2,3]) {
        const s={...stopped,metrics:{...stopped.metrics,state,speed_raw:state===1?2000:0}};
        assert.equal(Model.view(s,false).canStartPause,false);
        assert.equal(Model.view(s,false).canStop,true);
        assert.equal(Model.view(s,true).canStartPause,state!==0);
    }
    assert.equal(Model.view({...stopped,stopping:true},true).canStartPause,false);
    for(const fault of [{stale:true},{blocked:true},{storage_fault:'full'},{session:{status:'interrupted'}}])
        assert.equal(Model.view({...stopped,...fault},true).canStartPause,false);
    assert.equal(Model.view({...stopped,metrics:{...stopped.metrics,state:2}},false).canTakeControl,false);
});
test('native metrics show American units, unavailable values and simulator clearly',()=>{
    const v=Model.view(stopped,true);assert.equal(v.speed,'0.00 mph');assert.equal(v.distance,'1.000 mi');assert.equal(v.calories,'30 Cal');
    assert.equal(v.duration,'10m 0s');assert.equal(v.state,'Stopped');
    assert.equal(Model.view({...stopped,stale:true},true).speed,'—');
    assert.equal(Model.view({...stopped,connected:false},true).canStop,false);
    assert.match(Model.view({...stopped,simulator:true},false).label,/SIMULATOR/);
});
test('native targets quantize to valid exact hardware limits',()=>{
    assert.equal(Model.targetUnits(.1),1000);assert.equal(Model.targetUnits(20),6000);
    assert.equal(Model.targetUnits(2),3200);assert.equal(Model.targetUnits(2.1),3400);
    assert.throws(()=>Model.targetUnits(NaN));
});
