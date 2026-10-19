const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.join(__dirname, '..');

// Synthetic 53-byte idle report matching the observed 0x66 layout. Device
// identity bytes are zeroed; no serial number from the user's log is retained.
const IDLE_66 = '663500000000000000000000000000000000000000000000002582177000050200000000000000000000000000000000000000f243';

// Run the real dashboard without a physical Bluetooth device or browser storage.
function dashboard(history = [], failBackup = false, { currentSession = null, rawHistory = JSON.stringify(history), transport = null } = {}) {
    let exported;
    let createdCount = 0;
    let timerId = 0;
    const timers = new Map();
    const nodes = new Map();
    const node = id => {
        if (!nodes.has(id)) nodes.set(id, {
            textContent: '', innerHTML: '', value: '1', style: {}, disabled: false,
            classList: { add() {}, remove() {} }, listeners: {}, children: [],
            addEventListener(type, fn) { this.listeners[type] = fn; },
            querySelector() { return node(id + '-text'); },
            appendChild(child) { this.children.push(child); },
            replaceChildren() { this.children = []; this.innerHTML = ''; },
            click() {},
        });
        return nodes.get(id);
    };
    const storage = new Map([['treadmill_sessions', rawHistory]]);
    if (currentSession) storage.set('treadmill_current_session', JSON.stringify(currentSession));
    const context = vm.createContext({
        document: { getElementById: node, createElement: () => node('created-' + createdCount++),
            body: { appendChild() {}, removeChild() {} } },
        localStorage: { getItem: k => storage.get(k) ?? null,
            setItem: (k, v) => {
                if (failBackup && k === 'treadmill_sessions_backup_v1') throw new Error('Storage full');
                storage.set(k, v);
            }, removeItem: k => storage.delete(k) },
        ...(transport ? {PitPatTransports:{select:async()=>transport},fetch:()=>{},WebSocket:function(){},location:{origin:'http://127.0.0.1:8766'}} : {}),
        window: {}, navigator: {}, console: { log() {}, error() {} },
        setTimeout: (fn, delay) => { timers.set(++timerId, { fn, delay }); return timerId; },
        clearTimeout: id => timers.delete(id),
        Blob, URL: { createObjectURL(blob) { exported = blob; return 'blob:test'; }, revokeObjectURL() {} },
        FileReader: class { readAsText(file) { this.onload({ target: { result: file.content } }); } },
    });
    for (const file of ['walks.js', 'protocol.js', 'treadmill.js']) {
        if (fs.existsSync(path.join(root, file))) vm.runInContext(fs.readFileSync(path.join(root, file), 'utf8'), context);
    }
    return { node, storage, get exported() { return exported; }, run: code => vm.runInContext(code, context),
        bridge: (command = () => Promise.resolve({})) => {
            const commands = [];
            let listener;
            const transport = {kind:'bridge', simulator:true,
                onEvent(callback) { listener = callback; },
                command(op, args) { commands.push({op,args}); return command(op,args); },
                stop() { commands.push({op:'stop'}); return Promise.resolve({confirmed:true}); },
                stopDisconnect() {
                    commands.push({op:'stop_disconnect'});
                    listener({event:'disconnected',data:{confirmed:true}});
                    return Promise.resolve({confirmed:true});
                }};
            context.fakeTransport = transport;
            vm.runInContext('selectedTransport = fakeTransport; bindBridgeTransport(fakeTransport)', context);
            return {commands, emit: event => listener(event)};
        },
        flush: async () => { for (let i = 0; i < 15; i++) await Promise.resolve(); },
        expireStop: () => { for (const timer of [...timers.values()]) if (timer.delay === 5000) timer.fn(); },
        rawNotify: hex => {
            const bytes = Uint8Array.from(Buffer.from(hex, 'hex'));
            context.notification = { target: { value: new DataView(bytes.buffer) } };
            vm.runInContext('handleNotification(notification)', context);
        },
        bluetooth: (write = () => Promise.resolve()) => {
            const writes = [], disconnects = [];
            const gatt = { connected: true, disconnect() {
                disconnects.push('disconnect'); this.connected = false;
                vm.runInContext('onDisconnected()', context);
            } };
            context.fakeDevice = { gatt };
            context.fakeWrite = { writeValue(packet) { writes.push(Array.from(packet)); return write(packet); } };
            vm.runInContext('device = fakeDevice; writeChar = fakeWrite; connected = true;', context);
            return { writes, disconnects, gatt };
        },
        notify: (imperial, speed, distance = 1000, { state = 1, steps = 1200, calories = 75, duration = 600 } = {}) => {
            const bytes = new DataView(new ArrayBuffer(31));
            bytes.setUint8(0, 0x67); bytes.setUint8(1, 31); bytes.setUint8(30, 0x43);
            bytes.setUint16(3, speed); bytes.setUint32(7, distance);
            bytes.setUint32(14, steps); bytes.setUint16(18, calories);
            bytes.setUint32(20, duration * 1000);
            bytes.setUint8(26, [24, 8, 16, 0][state] | (imperial ? 128 : 0));
            let checksum = 0;
            for (let i = 1; i < 29; i++) checksum ^= bytes.getUint8(i);
            bytes.setUint8(29, checksum);
            context.notification = { target: { value: bytes } };
            vm.runInContext('handleNotification(notification)', context);
        },
    };
}

test('bridge telemetry preserves units and never sends a browser heartbeat', async () => {
    const app = dashboard(); const bridge = app.bridge();
    bridge.emit({event:'state',data:{connected:true,blocked:false}});
    const fixture = require('./fixtures/protocol.json')[0];
    bridge.emit({event:'telemetry',data:{hex:fixture.hex}}); await app.flush();
    assert.equal(app.node('speed').textContent, '1.99 mph');
    assert.equal(app.node('calories').textContent, '75 Cal');
    assert.equal(bridge.commands.length, 0);
    app.node('speedUpBtn').listeners.click(); await app.flush();
    assert.equal(bridge.commands[0].op, 'set_speed');
    assert.equal(bridge.commands[0].args.speed % 100, 0);
});

test('bridge Stop works with pending telemetry and successful disconnect stays confirmed', async () => {
    const app = dashboard(); const bridge = app.bridge();
    bridge.emit({event:'state',data:{connected:true,blocked:true}});
    assert.equal(app.node('stopBtn').disabled, false);
    assert.equal(await app.run('requestStop()'), true);
    assert.equal(await app.run('disconnectBluetooth()'), true);
    assert.match(app.node('safetyStatus').textContent, /Stopped confirmed before/);
    assert.equal(app.node('connectBtn').textContent, 'Connect');
});

test('bridge storage failures leave Stop usable and telemetry visible', async () => {
    const app = dashboard([], true); const bridge = app.bridge();
    bridge.emit({event:'state',data:{connected:true,blocked:false}});
    bridge.emit({event:'telemetry',data:{hex:require('./fixtures/protocol.json')[0].hex}});
    assert.equal(app.node('speed').textContent, '1.99 mph');
    assert.equal(await app.run('requestStop()'), true);
    assert.equal(bridge.commands.at(-1).op, 'stop');
});

test('obsolete bridge command failure cannot overwrite a confirmed disconnect', async () => {
    let reject;
    const app = dashboard(); const bridge = app.bridge(() => new Promise((_, fail) => {reject = fail;}));
    bridge.emit({event:'state',data:{connected:true,blocked:false}});
    app.run('send_data(makePacket("start"))');
    await app.run('disconnectBluetooth()');
    reject(Error('obsolete cancelled motion')); await app.flush();
    assert.match(app.node('safetyStatus').textContent, /Stopped confirmed before/);
});

test('Stop invalidates a queued bridge motion failure on the same connection', async () => {
    let reject;
    const app = dashboard(); const bridge = app.bridge(() => new Promise((_, fail) => {reject = fail;}));
    bridge.emit({event:'state',data:{connected:true,blocked:false}});
    app.run('send_data(makePacket("start"))');
    await app.run('requestStop()');
    reject(Error('cancelled by Stop')); await app.flush();
    assert.match(app.node('safetyStatus').textContent, /reported stopped with zero speed/);
});

test('Stop & Disconnect requested during Stop still disconnects after confirmation', async () => {
    const app = dashboard(); const bridge = app.bridge();
    bridge.emit({event:'state',data:{connected:true,blocked:true}});
    app.run('var resolveBridgeStop; selectedTransport.stop = () => new Promise(resolve => { resolveBridgeStop = resolve; })');
    const stop = app.run('requestStop()');
    const disconnect = app.run('disconnectBluetooth()');
    app.run('resolveBridgeStop({confirmed:true})');
    await stop; await disconnect;
    assert.ok(bridge.commands.some(command => command.op === 'stop_disconnect'));
    assert.equal(app.run('connected'), false);
});

test('metric telemetry converts speed and distance to American units', () => {
    const app = dashboard(); app.notify(false, 6000);
    assert.equal(app.node('speed').textContent, '3.73 mph');
    assert.equal(app.node('distance').textContent, '0.62 mi');
    assert.equal(app.node('calories').textContent, '75 Cal');
});

test('fresh starting and running reports replace the previous stopped indication', () => {
    const app = dashboard(); app.bluetooth();
    app.notify(false, 0, 0, {state:3});
    app.notify(false, 0, 0, {state:0});
    assert.equal(app.node('statusChip-text').textContent, 'Starting');
    assert.doesNotMatch(app.node('safetyStatus').textContent, /stopped with zero/);
    app.notify(false, 1000, 0, {state:1});
    assert.equal(app.node('statusChip-text').textContent, 'Running');
    assert.doesNotMatch(app.node('safetyStatus').textContent, /stopped with zero/);
});

test('a valid 53-byte 0x66 idle report enables controls and receives a heartbeat', async () => {
    const app = dashboard(); const ble = app.bluetooth();
    app.run('motionBlocked = true');
    app.rawNotify(IDLE_66); await app.flush();
    assert.equal(app.node('speed').textContent, '0.00 mph');
    assert.equal(app.node('statusChip-text').textContent, 'Stopped');
    assert.equal(app.node('startBtn').disabled, false);
    assert.deepEqual(ble.writes, [[0x6a, 0x05, 0xfd, 0xf8, 0x43]]);
    assert.equal(app.storage.get('treadmill_sessions'), '[]');
});

test('a fresh 0x66 stopped report can confirm Stop and Disconnect', async () => {
    const app = dashboard(); const ble = app.bluetooth();
    app.notify(true, 2000);
    const result = app.run('disconnectBluetooth()'); await app.flush();
    app.rawNotify(IDLE_66);
    await app.flush(); app.expireStop();
    assert.equal(await result, true);
    assert.equal(ble.disconnects.length, 1);
});

test('a heartbeat rejected after confirmed disconnect cannot overwrite the stop result', async () => {
    let rejectHeartbeat;
    const app = dashboard(); const ble = app.bluetooth(packet => packet.length === 5
        ? new Promise((resolve, reject) => { rejectHeartbeat = reject; }) : Promise.resolve());
    const result = app.run('disconnectBluetooth()'); await app.flush();
    app.rawNotify(IDLE_66); await app.flush();
    assert.equal(await result, true);
    assert.equal(ble.disconnects.length, 1);
    const confirmed = app.node('safetyStatus').textContent;
    assert.match(confirmed, /stopped confirmed/i);
    assert.equal(typeof rejectHeartbeat, 'function');
    rejectHeartbeat(new Error('GATT disconnected')); await app.flush();
    assert.equal(app.node('safetyStatus').textContent, confirmed);
});

test('a heartbeat failure on the current connection still warns about command failure', async () => {
    const app = dashboard(); app.bluetooth(() => Promise.reject(new Error('Write failed')));
    app.rawNotify(IDLE_66); await app.flush();
    assert.match(app.node('safetyStatus').textContent, /command failed/i);
});

test('an old heartbeat failure cannot overwrite a replacement connection state', async () => {
    let rejectHeartbeat;
    const app = dashboard(); app.bluetooth(() => new Promise((resolve, reject) => { rejectHeartbeat = reject; }));
    app.rawNotify(IDLE_66); await app.flush();
    app.run('onDisconnected()'); app.bluetooth(); app.rawNotify(IDLE_66); await app.flush();
    const current = app.node('safetyStatus').textContent;
    rejectHeartbeat(new Error('Old connection closed')); await app.flush();
    assert.equal(app.node('safetyStatus').textContent, current);
    assert.equal(app.node('startBtn').disabled, false);
});

test('a corrupt 0x66 report cannot unlock motion or confirm Stop', async () => {
    const app = dashboard(); const ble = app.bluetooth();
    const result = app.run('disconnectBluetooth()'); await app.flush();
    app.rawNotify(IDLE_66.slice(0, -4) + '0043'); await app.flush();
    assert.equal(app.node('startBtn').disabled, true);
    assert.equal(ble.disconnects.length, 0);
    app.expireStop(); assert.equal(await result, false);
});

test('Disconnect writes Stop immediately and waits for a fresh zero-speed stopped report', async () => {
    const app = dashboard(); const ble = app.bluetooth();
    app.notify(true, 2000);
    app.run('send_data(makePacket("start", 3200))');
    const result = app.run('disconnectBluetooth()'); await app.flush();
    assert.ok(ble.writes.some(p => p.length === 23 && p[12] === 0));
    assert.equal(ble.disconnects.length, 0);
    app.notify(true, 0, 1000, { state: 3 });
    assert.equal(await result, true);
    assert.equal(ble.disconnects.length, 1);
    assert.equal(app.run('pendingData'), null);
    assert.equal(ble.writes.filter(p => p.length === 23 && p[12] === 4).length, 0);
});

test('a stale stopped report cannot authorize disconnect; timeout leaves BLE connected', async () => {
    const app = dashboard(); const ble = app.bluetooth();
    app.notify(true, 0, 1000, { state: 3 });
    const result = app.run('disconnectBluetooth()'); await app.flush();
    app.expireStop();
    assert.equal(await result, false); assert.equal(ble.disconnects.length, 0);
    assert.match(app.node('safetyStatus').textContent, /physical stop/i);
});

test('a failed Stop write keeps BLE open and blocks motion commands', async () => {
    const app = dashboard(); const ble = app.bluetooth(() => Promise.reject(new Error('Write failed')));
    const result = app.run('disconnectBluetooth()');
    assert.equal(await result, false); assert.equal(ble.disconnects.length, 0);
    app.run('send_data(makePacket("start", 3200))');
    assert.equal(app.run('pendingData'), null);
    assert.match(app.node('safetyStatus').textContent, /physical stop/i);
});

test('unexpected link loss clears pending motion and warns that Stop is unconfirmed', () => {
    const app = dashboard(); app.bluetooth(); app.notify(true, 2000);
    app.run('send_data(makePacket("start", 3200)); onDisconnected()');
    assert.equal(app.run('pendingData'), null);
    assert.match(app.node('safetyStatus').textContent, /may still be moving/i);
    assert.equal(app.run('writeChar'), null);
});

test('Stop stays available during the starting state and writes without another notification', async () => {
    const app = dashboard(); const ble = app.bluetooth();
    app.run('updateRunningState(0)'); assert.equal(app.node('stopBtn').disabled, false);
    const result = app.node('stopBtn').listeners.click(); await app.flush();
    assert.ok(ble.writes.some(p => p.length === 23 && p[12] === 0));
    app.notify(true, 0, 1000, { state: 3 }); await result;
    assert.equal(ble.disconnects.length, 0);
});

test('stopped flags with nonzero speed cannot confirm Stop or end a walk', async () => {
    const app = dashboard(); const ble = app.bluetooth(); app.notify(true, 2000);
    const result = app.run('disconnectBluetooth()'); await app.flush();
    app.notify(true, 1000, 1000, { state: 3 }); await app.flush();
    assert.equal(ble.disconnects.length, 0);
    assert.notEqual(JSON.parse(app.storage.get('treadmill_sessions'))[0].status, 'completed');
    app.notify(true, 0, 1000, { state: 3 });
    assert.equal(await result, true);
});

test('malformed telemetry cannot falsely confirm Stop', async () => {
    const app = dashboard(); const ble = app.bluetooth();
    const result = app.run('disconnectBluetooth()'); await app.flush();
    app.run('handleNotification({target:{value:new DataView(new ArrayBuffer(31))}})');
    await app.flush(); assert.equal(ble.disconnects.length, 0);
    app.expireStop(); assert.equal(await result, false);
});

test('invalid telemetry preserves stale readings and does not claim Bluetooth disconnected after Stop timeout', async () => {
    const app = dashboard(); const ble = app.bluetooth();
    app.notify(true, 2000);
    const speed = app.node('speed').textContent;
    const result = app.run('disconnectBluetooth()'); await app.flush();
    app.run('handleNotification({target:{value:new DataView(new ArrayBuffer(31))}})');
    app.expireStop(); assert.equal(await result, false);
    assert.equal(ble.gatt.connected, true);
    assert.equal(app.node('speed').textContent, speed);
    assert.match(app.node('statusChip-text').textContent, /telemetry.*unavailable/i);
    assert.match(app.node('statusChip-text').textContent, /stale/i);
    assert.equal(app.node('startBtn').disabled, true);
    assert.equal(app.node('stopBtn').disabled, false);
    assert.equal(ble.disconnects.length, 0);
});

test('losing BLE while waiting for Stop never reports a successful disconnect', async () => {
    const app = dashboard(); app.bluetooth(); app.notify(true, 2000);
    const result = app.run('disconnectBluetooth()'); await app.flush();
    app.run('onDisconnected()');
    assert.equal(await result, false);
    assert.match(app.node('safetyStatus').textContent, /physical stop/i);
});

test('timeout bounds an unresolved GATT write even after a stopped report arrives', async () => {
    const app = dashboard(); const ble = app.bluetooth(() => new Promise(() => {}));
    const result = app.run('disconnectBluetooth()'); await app.flush();
    app.notify(true, 0, 1000, { state: 3 });
    app.expireStop(); await app.flush();
    assert.equal(app.run('disconnectInProgress'), false);
    assert.equal(await result, false); assert.equal(ble.disconnects.length, 0);
    assert.equal(app.node('connectBtn').disabled, false);
});

test('connection loss cancels an unresolved Stop write after a stopped report', async () => {
    const app = dashboard(); app.bluetooth(() => new Promise(() => {}));
    const result = app.run('disconnectBluetooth()'); await app.flush();
    app.notify(true, 0, 1000, { state: 3 }); app.run('onDisconnected()'); await app.flush();
    assert.equal(app.run('disconnectInProgress'), false);
    assert.equal(await result, false);
});

test('Stop cancels already-queued motion behind an in-flight GATT write', async () => {
    let release;
    let calls = 0;
    const app = dashboard();
    const ble = app.bluetooth(() => ++calls === 1 ? new Promise(resolve => { release = resolve; }) : Promise.resolve());
    app.notify(true, 2000); await app.flush(); // heartbeat is already in flight
    app.run('send_data(makePacket("start", 3200))'); app.notify(true, 2000);
    const result = app.run('disconnectBluetooth()');
    release(); await app.flush();
    assert.equal(ble.writes.filter(p => p.length === 23 && p[12] === 4).length, 0);
    app.notify(true, 0, 1000, { state: 3 });
    assert.equal(await result, true);
});

test('a completed walk retains distance and final stopped counters for Notion', () => {
    const app = dashboard();
    app.notify(true, 2000, 500, { duration: 900 });
    app.notify(true, 0, 1000, { state: 3, duration: 1800, steps: 2500, calories: 100 });
    const walk = JSON.parse(app.storage.get('treadmill_sessions'))[0];
    assert.equal(walk.distanceMiles, 1);
    assert.equal(walk.duration, 1800); assert.equal(walk.steps, 2500);
    assert.equal(walk.status, 'completed');
    assert.ok(walk.sessionId); assert.ok(walk.endedAt);
});

test('pause and resume retain one stable walk identity', () => {
    const app = dashboard(); app.notify(true, 2000);
    const id = JSON.parse(app.storage.get('treadmill_sessions'))[0].sessionId;
    assert.ok(id);
    app.notify(true, 0, 1000, { state: 2 });
    app.notify(true, 2000, 1100, { duration: 660 });
    app.notify(true, 0, 1200, { state: 3, duration: 720 });
    const walks = JSON.parse(app.storage.get('treadmill_sessions'));
    assert.equal(walks.length, 1); assert.equal(walks[0].sessionId, id);
    assert.equal(walks[0].status, 'completed');
});

test('disconnect preserves an interrupted walk without pretending it stopped', () => {
    const app = dashboard(); app.notify(true, 2000);
    app.run('onDisconnected()');
    const walk = JSON.parse(app.storage.get('treadmill_sessions'))[0];
    assert.equal(walk.status, 'interrupted'); assert.equal(walk.endReason, 'Disconnected');
    assert.ok(app.storage.get('treadmill_current_session'));
});

test('Notion preparation previews known metrics and repeated export keeps stable IDs', async () => {
    const app = dashboard(); app.notify(true, 2000, 1000, { duration: 1800, calories: 100, steps: 2500 });
    app.notify(true, 0, 1000, { state: 3, duration: 1800, calories: 100, steps: 2500 });
    assert.equal(typeof app.node('prepareNotionBtn').listeners.click, 'function');
    app.node('prepareNotionBtn').listeners.click();
    assert.ok(app.node('notionPreview').children.length > 0);
    app.node('downloadNotionBtn').listeners.click();
    const first = JSON.parse(await app.exported.text());
    app.node('prepareNotionBtn').listeners.click(); app.node('downloadNotionBtn').listeners.click();
    const second = JSON.parse(await app.exported.text());
    assert.equal(first.walks[0].sourceId, second.walks[0].sourceId);
    assert.equal(first.walks[0].properties.Type, 'Walking');
    assert.equal(first.walks[0].properties.Source, 'Walking Pad');
    assert.equal(first.walks[0].properties['Distance Miles'], 1);
    assert.equal(first.walks[0].properties['Duration Minutes'], 30);
    assert.equal(first.walks[0].properties['Calories kcal'], 100);
    assert.equal(first.walks[0].metrics.cadenceStepsPerMinute, 2500 / 30);
    assert.equal(first.walks[0].metrics.paceMinutesPerMile, 30);
});

test('legacy walks get persistent IDs but unknown distance stays absent from Notion', () => {
    const app = dashboard([{ date: 1000000000000, duration: 60, steps: 100, avgSpeed: 2, speedUnit: 'mph', calories: '5 Cal' }]);
    const sessions = JSON.parse(app.storage.get('treadmill_sessions'));
    assert.ok(sessions[0].sessionId);
    const bundle = JSON.parse(app.run('JSON.stringify(buildNotionExport(loadSessions()))'));
    assert.equal(bundle.walks.length, 1);
    assert.equal(bundle.walks[0].properties['Distance Miles'], undefined);
    assert.equal(bundle.walks[0].properties['Data Quality'], 'Partial');
});

test('a stopped counter reset preserves the last observed walk totals', () => {
    const app = dashboard(); app.notify(true, 2000, 1000, { duration: 1800 });
    app.notify(true, 0, 0, { state: 3, duration: 0, steps: 0, calories: 0 });
    const walk = JSON.parse(app.storage.get('treadmill_sessions'))[0];
    assert.equal(walk.distanceMiles, 1); assert.equal(walk.duration, 1800);
    assert.equal(walk.status, 'completed'); assert.equal(walk.coverage, 'partial');
});

test('reconnect requires a tracking decision and then keeps the same walk ID', () => {
    const app = dashboard(); app.notify(true, 2000);
    const id = JSON.parse(app.storage.get('treadmill_sessions'))[0].sessionId;
    app.run('onDisconnected(); connected = true');
    app.notify(true, 2000, 1100, { duration: 660 });
    assert.equal(JSON.parse(app.storage.get('treadmill_sessions'))[0].distanceMiles, 1);
    app.node('continueWalkBtn').listeners.click();
    app.notify(true, 2000, 1200, { duration: 720 });
    const walks = JSON.parse(app.storage.get('treadmill_sessions'));
    assert.equal(walks.length, 1); assert.equal(walks[0].sessionId, id);
    assert.equal(walks[0].distanceMiles, 1.2);
});

test('history imports merge new records and repeated imports keep existing walks', () => {
    const app = dashboard([{ date: 1, duration: 60, steps: 100 }]);
    const imported = JSON.stringify([{ date: 2, duration: 120, steps: 200 }]);
    app.node('importHistoryInput').files = [{ content: imported }];
    app.node('importHistoryInput').listeners.change();
    app.node('importHistoryInput').listeners.change();
    const walks = JSON.parse(app.storage.get('treadmill_sessions'));
    assert.equal(walks.length, 2);
    assert.deepEqual(walks.map(w => w.date).sort(), [1, 2]);
});

test('export excludes paused walks until they are stopped', () => {
    const app = dashboard(); app.notify(true, 2000); app.notify(true, 0, 1000, { state: 2 });
    const result = JSON.parse(app.run('JSON.stringify(buildNotionExport(loadSessions()))'));
    assert.equal(result.walks.length, 0); assert.equal(result.excluded.length, 1);
});

test('a new tracking update invalidates a previously prepared Notion snapshot', () => {
    const app = dashboard(); app.notify(true, 2000); app.notify(true, 0, 1000, { state: 3 });
    app.node('prepareNotionBtn').listeners.click();
    assert.equal(app.node('downloadNotionBtn').disabled, false);
    app.notify(true, 2000);
    assert.equal(app.node('downloadNotionBtn').disabled, true);
});

test('a new record after interruption counts only increments after its boundary', () => {
    const app = dashboard(); app.notify(true, 2000, 1000, { duration: 1800 });
    app.run('onDisconnected(); connected = true');
    app.node('newWalkRecordBtn').listeners.click();
    app.notify(true, 2000, 1100, { duration: 1980, steps: 2600, calories: 110 });
    app.notify(true, 0, 1200, { state: 3, duration: 2160, steps: 2800, calories: 120 });
    const walks = JSON.parse(app.storage.get('treadmill_sessions'));
    assert.equal(walks.length, 2);
    assert.ok(Math.abs(walks[0].distanceMiles - 0.1) < 1e-10);
    assert.equal(walks[0].duration, 180); assert.equal(walks[0].steps, 200);
    assert.equal(walks[0].calories, '10 Cal');
    assert.equal(walks[1].distanceMiles, 1);
});

test('imperial telemetry is not converted twice', () => {
    const app = dashboard(); app.notify(true, 2000);
    assert.equal(app.node('speed').textContent, '2.00 mph');
    assert.equal(app.node('distance').textContent, '1.00 mi');
    assert.equal(app.node('calories').textContent, '75 Cal');
});

test('MPH input creates a metric packet with a valid checksum', () => {
    const app = dashboard(); app.run('connected = true');
    app.node('speedSlider').value = '2'; app.node('speedSlider').listeners.change();
    const packet = Array.from(app.run('pendingData'));
    assert.equal((packet[6] << 8) | packet[7], 3200);
    assert.equal(packet[12], 4);
    assert.equal(packet.slice(1, 21).reduce((a, b) => a ^ b, 0), packet[21]);
    assert.equal(app.node('sliderValue').textContent, '1.99');
});

test('MPH endpoint rounding never exceeds existing physical speed limits', () => {
    const app = dashboard(); app.run('connected = true');
    for (const [value, expected] of [['0.62', 1000], ['3.73', 6000], ['100', 6000], ['-1', 1000]]) {
        app.node('speedSlider').value = value; app.node('speedSlider').listeners.change();
        assert.equal(app.run('curTargetSpeed'), expected);
    }
});

test('both speed buttons adjust MPH and keep the slider synchronized', () => {
    const app = dashboard(); app.run('connected = true; curTargetSpeed = 3200');
    app.node('speedUpBtn').listeners.click();
    assert.equal(app.run('curTargetSpeed'), 3400);
    assert.equal(app.node('sliderValue').textContent, '2.11');
    app.node('speedDownBtn').listeners.click();
    assert.equal(app.run('curTargetSpeed'), 3200);
    assert.equal(app.node('sliderValue').textContent, '1.99');
});

test('invalid MPH input queues no command', () => {
    const app = dashboard(); app.run('connected = true');
    app.node('speedSlider').value = 'not-a-number'; app.node('speedSlider').listeners.change();
    assert.equal(app.run('pendingData'), null);
});

test('legacy history migrates once with original measurements and exact backup', () => {
    const original = [{ date: 1, duration: 60, steps: 100, avgSpeed: 6, speedUnit: 'kph', calories: '75 kcal' }];
    const app = dashboard(original);
    const migrated = JSON.parse(app.storage.get('treadmill_sessions'))[0];
    assert.equal(migrated.schemaVersion, 2);
    assert.ok(Math.abs(migrated.avgSpeed - 3.728227153424004) < 1e-10);
    assert.equal(migrated.speedUnit, 'mph'); assert.equal(migrated.calories, '75 Cal');
    assert.equal(migrated.originalMeasurements.avgSpeed, 6);
    assert.equal(app.storage.get('treadmill_sessions_backup_v1'), JSON.stringify(original));
    const once = JSON.stringify(app.run('loadSessions()'));
    assert.equal(JSON.stringify(app.run('loadSessions()')), once);
    assert.equal(app.storage.get('treadmill_sessions_backup_v1'), JSON.stringify(original));
});

test('history retains imperial speed and leaves unknown speed units unconverted', () => {
    const app = dashboard([{ avgSpeed: 2, speedUnit: 'mph', calories: '50 kcal' }, { avgSpeed: 4, calories: 'unknown' }]);
    const history = JSON.parse(app.storage.get('treadmill_sessions'));
    assert.equal(history[0].avgSpeed, 2); assert.equal(history[0].calories, '50 Cal');
    assert.equal(history[1].avgSpeed, 4); assert.equal(history[1].calories, 'unknown');
});

test('new sessions store MPH and Calories while retaining raw telemetry', () => {
    const app = dashboard(); app.notify(false, 6000);
    const session = JSON.parse(app.storage.get('treadmill_sessions'))[0];
    assert.equal(session.schemaVersion, 2); assert.equal(session.speedUnit, 'mph');
    assert.equal(session.calories, '75 Cal'); assert.equal(session.sourceTelemetry.speed_unit, 'kph');
    assert.equal(session.sourceTelemetry.current_speed, 6000);
});

test('session speed averages remain correct if device unit mode changes', () => {
    const app = dashboard(); app.notify(false, 6000); app.notify(true, 2000);
    const session = JSON.parse(app.storage.get('treadmill_sessions'))[0];
    assert.ok(Math.abs(session.avgSpeed - 2.864113576712002) < 1e-10);
});

test('exported JSON carries normalized units and original measurements', async () => {
    const app = dashboard([{ avgSpeed: '6', speedUnit: 'kph', calories: '75 kcal' }]);
    app.node('exportHistoryBtn').listeners.click();
    const records = JSON.parse(await app.exported.text());
    assert.equal(records[0].schemaVersion, 2);
    assert.equal(records[0].speedUnit, 'mph'); assert.equal(records[0].calories, '75 Cal');
    assert.equal(records[0].originalMeasurements.speedUnit, 'kph');
    assert.equal(records[0].originalMeasurements.calories, '75 kcal');
});

test('a failed backup leaves the stored history untouched and blocks later writes', () => {
    const original = [{ avgSpeed: 6, speedUnit: 'kph', calories: '75 kcal' }];
    const app = dashboard(original, true);
    assert.equal(app.storage.get('treadmill_sessions'), JSON.stringify(original));
    assert.throws(() => app.run('saveSessions([])'), /Storage full/);
    assert.equal(app.storage.get('treadmill_sessions'), JSON.stringify(original));
});

test('zero telemetry is displayed as zero with its units', () => {
    const app = dashboard(); app.notify(false, 0, 0);
    assert.equal(app.node('speed').textContent, '0.00 mph');
    assert.equal(app.node('distance').textContent, '0.00 mi');
});

test('out-of-range and non-finite protocol speeds cannot create motion packets', () => {
    const app = dashboard();
    for (const speed of ['0', '6001', 'NaN', 'Infinity', '3200.5']) {
        assert.throws(() => app.run(`makePacket('set_speed', ${speed})`), /Command speed/);
    }
});

test('migration backup preserves the original JSON whitespace exactly', () => {
    const rawHistory = '[\n  { "avgSpeed": 6, "speedUnit": "kph", "calories": "75 kcal" }\n]\n';
    const app = dashboard([], false, { rawHistory });
    assert.equal(app.storage.get('treadmill_sessions_backup_v1'), rawHistory);
    assert.equal(JSON.parse(app.storage.get('treadmill_sessions'))[0].speedUnit, 'mph');
});

test('restoring a legacy unfinished metric session converts its accumulated speeds once', () => {
    const app = dashboard([], false, { currentSession: { date: 1, speedSum: 12000,
        speedCount: 2, speedUnit: 'kph', duration: 60, calories: 10, steps: 100 } });
    app.run('connected = true');
    app.node('continueWalkBtn').listeners.click();
    app.notify(true, 2000);
    const session = JSON.parse(app.storage.get('treadmill_sessions'))[0];
    assert.equal(session.speedUnit, 'mph');
    assert.ok(Math.abs(session.avgSpeed - 3.152151435616003) < 1e-10);
});

test('shared bridge observer never records locally and cannot move the belt',async()=>{
    const app=dashboard();const bridge=app.bridge();
    app.run("selectedTransport.recording='bridge'; selectedTransport.observers=true");
    const before=app.storage.get('treadmill_sessions');
    bridge.emit({event:'state',data:{connected:true,blocked:false},snapshot:{connected:true,is_owner:false,owner_kind:'tray',blocked:false,stale:false}});
    const fixture=require('./fixtures/protocol.json')[0];
    bridge.emit({event:'telemetry',data:{hex:fixture.hex},snapshot:{connected:true,is_owner:false,owner_kind:'tray',blocked:false,stale:false}});
    assert.equal(app.node('startBtn').disabled,true);
    assert.equal(app.node('stopBtn').disabled,false);
    app.node('speedUpBtn').listeners.click();await app.flush();
    assert.deepEqual(bridge.commands,[]);
    assert.equal(app.storage.get('treadmill_sessions'),before);
    assert.equal(app.storage.get('treadmill_current_session'),undefined);
});

test('shared bridge page load preserves exact legacy history and pending recovery bytes',async()=>{
    const raw='[ {"date":1000,"avgSpeed":2,"speedUnit":"kph","calories":"3 kcal"} ]';
    const current={date:1000,status:'running',speedSum:2000,speedCount:1,speedUnit:'kph'};
    let listener;
    const transport={kind:'bridge',observers:true,recording:'bridge',onEvent(cb){listener=cb;},
        observe:async()=>({is_owner:false}),walks:async()=>({walks:[],next_cursor:null})};
    const app=dashboard([] ,false,{rawHistory:raw,currentSession:current,transport});await app.flush();
    assert.equal(app.storage.get('treadmill_sessions'),raw);
    assert.equal(app.storage.get('treadmill_current_session'),JSON.stringify(current));
    assert.equal(app.storage.get('treadmill_sessions_backup_v1'),undefined);
});

test('shared history import waits for durable acknowledgement before reporting success',async()=>{
    let acknowledge, rows=[];
    const transport={kind:'bridge',observers:true,recording:'bridge',onEvent(){},observe:async()=>({is_owner:false}),
        walks:async()=>({walks:rows,next_cursor:null}),importWalks:records=>new Promise(resolve=>{
            acknowledge=()=>{rows=records;resolve({imported:1});};
        })};
    const app=dashboard([],false,{transport});await app.flush();
    const raw={schemaVersion:2,sessionId:'import-one',date:1000,status:'completed',duration:60};
    app.node('importHistoryInput').files=[{content:JSON.stringify([raw])}];
    app.node('importHistoryInput').listeners.change();await app.flush();
    assert.equal(rows.length,0);
    assert.notEqual(app.node('snackbar-text').textContent,'History saved to the bridge.');
    acknowledge();await app.flush();
    assert.equal(rows.length,1);
    assert.equal(app.node('snackbar-text').textContent,'History saved to the bridge.');
    assert.equal(app.storage.get('treadmill_sessions'),'[]');
    assert.equal(app.node('historyTableBody').children.at(-1).children.at(-1).children[0].disabled,true);
});

test('history update arriving during a fetch is refetched before refresh resolves',async()=>{
    let release, calls=0, hold=false;
    const active={schemaVersion:2,sessionId:'race-one',date:1000,status:'running'};
    const done={...active,status:'completed',duration:60};
    const transport={kind:'bridge',observers:true,recording:'bridge',onEvent(){},observe:async()=>({is_owner:false}),
        walks:()=>{
            calls++;
            if(hold && calls===2) return new Promise(resolve=>{release=()=>resolve({walks:[active],next_cursor:null});});
            return Promise.resolve({walks:hold?[done]:[],next_cursor:null});
        }};
    const app=dashboard([],false,{transport});await app.flush();
    hold=true;const first=app.run('refreshSharedHistory()');await app.flush();
    app.run('refreshSharedHistory()');release();await first;await app.flush();
    assert.equal(calls,3);
    assert.equal(app.run('sharedWalks[0].status'),'completed');
});
