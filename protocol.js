(function(root, factory) {
    const api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    else root.PitPatProtocol = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
    function parseTelemetry(bytes) {
        const value = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
        const n = value.byteLength;
        if (n < 31 || n > 255) throw new Error('Invalid telemetry size');
        let checksum = 0;
        for (let i = 1; i < n - 2; i++) checksum ^= value.getUint8(i);
        if ((value.getUint8(0) !== 0x67 && !(value.getUint8(0) === 0x66 && n === 53)) ||
            value.getUint8(1) !== n || value.getUint8(n - 1) !== 0x43 || value.getUint8(n - 2) !== checksum)
            throw new Error('Invalid telemetry framing');
        const flags = value.getUint8(26), imperial = !!(flags & 128);
        return {current_speed: value.getUint16(3), distance: value.getUint32(7), steps: value.getUint32(14),
            calories: value.getUint16(18), duration: value.getUint32(20), flags,
            running_state: {24: 0, 8: 1, 16: 2, 0: 3}[flags & 24],
            speed_unit: imperial ? 'mph' : 'kph', distance_unit: imperial ? 'mi' : 'km',
            packetHex: Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('')};
    }
    function makePacket(type, speed = 1000) {
        if (!['start', 'pause', 'stop', 'set_speed'].includes(type)) throw new RangeError('Unknown command');
        if (!Number.isInteger(speed) || speed < 1000 || speed > 6000 || speed % 100) throw new RangeError('Command speed must be 1000–6000 in steps of 100');
        const packet = new Uint8Array(23);
        packet[0] = 0x6a; packet[1] = 23; packet[6] = speed >> 8; packet[7] = speed & 255;
        packet[8] = type === 'set_speed' ? 5 : 1; packet[10] = 80;
        packet[12] = type === 'stop' ? 0 : type === 'pause' ? 2 : 4;
        const user = 58965456623n;
        for (let i = 0; i < 8; i++) packet[13 + i] = Number((user >> BigInt(56 - i * 8)) & 255n);
        for (let i = 1; i <= 20; i++) packet[21] ^= packet[i];
        packet[22] = 0x43;
        return packet;
    }
    return {parseTelemetry, makePacket};
});
