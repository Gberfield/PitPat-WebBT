// Writes tests/fixtures/model-cases.json from Model.js; the Swift menu bar port must match it.
const fs=require('node:fs'),path=require('node:path');
const Model=require('../integration/omarchy/gabe.pitpat/Model.js');
const metrics={speed_raw:0,state:3,unit_mode:0,distance:1609,steps:1000,calories:30,duration:600000};
const base={available:true,connected:true,blocked:false,stale:false,recovery:false,target_speed:1000,owner_present:true,owner_kind:'tray',metrics};
const walking={...base,target_speed:3200,metrics:{...metrics,state:1,speed_raw:3200,distance:2414,steps:4321,calories:57,duration:3723000}};
const snapshots={
  'unavailable':{available:false,connected:false},
  'empty':{},
  'disconnected':{available:true,connected:false,owner_present:false},
  'simulator-disconnected':{available:true,connected:false,simulator:true},
  'connecting':{available:true,connected:false,connecting:true},
  'stopped-owner':base,
  'stopped-observer-browser':{...base,owner_kind:'browser'},
  'stopped-no-owner':{...base,owner_present:false,owner_kind:null},
  'walking-owner':walking,
  'walking-observer':{...walking,owner_kind:'browser'},
  'paused-owner':{...walking,metrics:{...walking.metrics,state:2,speed_raw:0}},
  'starting-owner':{...base,metrics:{...metrics,state:0}},
  'imperial-walking':{...walking,metrics:{...walking.metrics,unit_mode:1,speed_raw:2000,distance:1500}},
  'stale':{...base,stale:true},
  'fault':{...base,fault_id:'f1',blocked:true},
  'recovery':{...base,recovery:true,fault_id:'f1'},
  'stopping':{...walking,stopping:true},
  'safety-unavailable':{...base,connected:false,safety_available:false},
  'storage-fault':{...base,storage_fault:'Disk full'},
  'interrupted-session':{...base,session:{status:'interrupted',sessionId:'s1'}},
  'blocked':{...base,blocked:true},
  'unknown-state':{...base,metrics:{...metrics,state:7}},
  'no-metrics':{...base,metrics:null},
  'zero-target':{...base,target_speed:0},
  'simulator-walking':{...walking,simulator:true,target_speed:6000},
  'hour-duration':{...base,metrics:{...metrics,duration:7200000}},
};
const cases=[];
for(const [name,snapshot] of Object.entries(snapshots))for(const isOwner of [false,true])
  cases.push({name,isOwner,snapshot,view:Model.view(snapshot,isOwner)});
const targets=[0.1,0.62,0.68,1,1.5,2,2.1,2.25,3.1,3.73,20,-1].map(mph=>({mph,units:Model.targetUnits(mph)}));
const out=path.join(__dirname,'fixtures','model-cases.json');
const text=JSON.stringify({cases,targets},null,1)+'\n';
if(process.argv.includes('--check')){if(fs.readFileSync(out,'utf8')!==text){console.error('model-cases.json is stale; run node tests/gen-model-cases.cjs');process.exit(1)}}
else fs.writeFileSync(out,text);
