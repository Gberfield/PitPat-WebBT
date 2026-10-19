const {test} = require('node:test');
const assert = require('node:assert/strict');
const {select, BridgeTransport} = require('../transports.js');

class Socket {
    static instances = [];
    constructor(url) { this.url = url; this.sent = []; this.readyState = 1; Socket.instances.push(this); queueMicrotask(() => this.onopen()); }
    send(text) { this.sent.push(JSON.parse(text)); }
    close() { this.readyState = 3; this.onclose?.(); }
    receive(data) { this.onmessage({data:JSON.stringify(data)}); }
}
const bootstrap = {v:1, transport:'bridge', token:'synthetic-token', simulator:true, lease_ms:6000};
const location = {origin:'http://127.0.0.1:8765'};
async function opened() {
    const transport = new BridgeTransport(bootstrap, {WebSocket:Socket, location});
    const open = transport.open(); await Promise.resolve();
    const socket = Socket.instances.at(-1);
    socket.receive({v:1,event:'authorized',generation:0}); await open;
    return {transport, socket};
}
test('select only falls back to direct on an absent endpoint', async () => {
    assert.equal((await select({fetch:async()=>({status:404}), bluetooth:{requestDevice(){}}, location})).kind, 'direct');
    await assert.rejects(select({fetch:async()=>({status:404}), bluetooth:null, location}), /bridge/i);
    await assert.rejects(select({fetch:async()=>{throw Error('offline');}, bluetooth:{requestDevice(){}}, location}), /offline/);
    await assert.rejects(select({fetch:async()=>({status:200,json:async()=>({})}), bluetooth:{requestDevice(){}}, location}), /Invalid/);
});
test('bootstrap fetch uses the browser global receiver, not the transport environment', async () => {
    const transport = await select({fetch:async function() {
        assert.equal(this, globalThis);
        return {status:200,json:async()=>bootstrap};
    }, WebSocket:Socket, location});
    assert.equal(transport.kind,'bridge');
});
test('old socket cannot resolve a new request or deliver old telemetry', async () => {
    const {transport, socket} = await opened(); const events = [];
    transport.onEvent(e=>events.push(e));
    const request = transport.command('discover'); await Promise.resolve();
    const id = socket.sent.at(-1).id;
    socket.receive({v:1,id,generation:0,ok:true,result:{devices:[]}});
    assert.deepEqual(await request, {devices:[]});
    transport.claimed = true;
    socket.receive({v:1,event:'state',generation:2,seq:2,data:{connected:true}});
    socket.receive({v:1,event:'telemetry',generation:1,seq:3,data:{hex:'bad'}});
    socket.receive({v:1,event:'telemetry',generation:2,seq:1,data:{hex:'bad'}});
    assert.equal(events.length, 1);
    const pending = transport.command('start'); await Promise.resolve();
    socket.close(); await assert.rejects(pending, /bridge/i);
    const replacement = transport.open(); await Promise.resolve();
    const next = Socket.instances.at(-1); next.receive({v:1,event:'authorized',generation:3}); await replacement;
    socket.receive({v:1,event:'telemetry',generation:99,seq:100,data:{hex:'bad'}});
    assert.equal(events.filter(e=>e.event==='telemetry').length, 0);
    next.close();
});
test('bridge telemetry never submits a raw heartbeat or replays motion', async () => {
    const {transport, socket} = await opened(); transport.claimed = true;
    for (let seq=1; seq<=2; seq++) socket.receive({v:1,event:'telemetry',generation:0,seq,data:{hex:'6635'}});
    assert.deepEqual(socket.sent.map(x=>x.op), ['authorize']);
    const start = transport.command('start', {speed:1000}); await Promise.resolve();
    socket.close(); await assert.rejects(start);
    assert.equal(socket.sent.filter(x=>x.op==='start').length, 1);
});

test('new bridge observes telemetry without renewing or claiming ownership', async t => {
    const transport=new BridgeTransport({...bootstrap,observers:true,recording:'bridge'}, {WebSocket:Socket,location});
    const opening=transport.open(); await Promise.resolve();const socket=Socket.instances.at(-1);t.after(()=>socket.close());
    const snapshot={connected:true,is_owner:false,owner_kind:'tray',blocked:false};
    socket.receive({v:1,event:'authorized',generation:2,snapshot});await opening;
    const events=[];transport.onEvent(e=>events.push(e));
    socket.receive({v:1,event:'telemetry',generation:2,seq:1,snapshot,data:{hex:'synthetic'}});
    assert.equal(events.filter(e=>e.event==='telemetry').length,1);
    assert.equal(transport.claimed,false);
    await new Promise(r=>setTimeout(r,1050));
    assert.deepEqual(socket.sent.map(r=>r.op),['authorize']);
});

test('takeControl accepts new generation but a late old motion cannot restore ownership', async t=>{
    const transport=new BridgeTransport({...bootstrap,observers:true}, {WebSocket:Socket,location});
    const opening=transport.open();await Promise.resolve();const socket=Socket.instances.at(-1);t.after(()=>socket.close());
    socket.receive({v:1,event:'authorized',generation:0,snapshot:{is_owner:false}});await opening;
    const take=transport.takeControl();await Promise.resolve();const id=socket.sent.at(-1).id;
    socket.receive({v:1,event:'ownership',generation:1,seq:1,snapshot:{is_owner:true},data:{}});
    socket.receive({v:1,id,generation:1,ok:true,result:{is_owner:true,generation:1}});
    await take;assert.equal(transport.claimed,true);
    const motion=transport.command('start');await Promise.resolve();const mid=socket.sent.at(-1).id;
    socket.receive({v:1,event:'ownership',generation:2,seq:2,snapshot:{is_owner:false},data:{}});
    socket.receive({v:1,id:mid,generation:1,ok:true,result:{written:true}});
    await assert.rejects(motion,/Obsolete/);assert.equal(transport.claimed,false);
});
