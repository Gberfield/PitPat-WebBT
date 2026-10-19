const {test} = require('node:test');
const assert = require('node:assert/strict');
const protocol = require('../protocol.js');
const fixtures = require('./fixtures/protocol.json');

test('shared protocol reports preserve state, counters and units', () => {
    for (const f of fixtures) {
        const raw = protocol.parseTelemetry(Buffer.from(f.hex, 'hex'));
        assert.equal(raw.current_speed, f.speed);
        assert.equal(raw.running_state, f.state);
        assert.equal(raw.steps, 1200);
        assert.equal(raw.duration, 600000);
        assert.equal(raw.speed_unit, f.imperial ? 'mph' : 'kph');
    }
});
test('bad framing never supplies treadmill state', () => {
    const good = Buffer.from(fixtures[0].hex, 'hex');
    for (const i of [0, 1, 4, good.length - 2, good.length - 1]) {
        const bad = Buffer.from(good); bad[i] ^= 1;
        assert.throws(() => protocol.parseTelemetry(bad));
    }
    for (let i = 0; i < 31; i++) assert.throws(() => protocol.parseTelemetry(good.subarray(0, i)));
});
test('commands reject invalid targets and preserve literal stop bytes', () => {
    for (const speed of [999, 6001, 1050, true, '1000', NaN]) assert.throws(() => protocol.makePacket('start', speed));
    assert.throws(() => protocol.makePacket('unknown'));
    assert.equal(Buffer.from(protocol.makePacket('stop')).toString('hex'), '6a170000000003e801005000000000000dba9d76ef1e43');
    assert.equal(protocol.makePacket('start', 6000)[12], 4);
});
