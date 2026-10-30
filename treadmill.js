// treadmill.js - JavaScript logic for PitPat Treadmill Control Dashboard

// --- Bluetooth UUIDs ---
const SERVICE_UUID = "0000fba0-0000-1000-8000-00805f9b34fb";
const NOTIFY_CHAR_UUID = "0000fba2-0000-1000-8000-00805f9b34fb";
const WRITE_CHAR_UUID = "0000fba1-0000-1000-8000-00805f9b34fb";

// --- UI Elements ---
const connectBtn = document.getElementById('connectBtn');
const statusDiv = document.getElementById('status');
const speedDiv = document.getElementById('speed');
const distanceDiv = document.getElementById('distance');
const caloriesDiv = document.getElementById('calories');
const stepsDiv = document.getElementById('steps');
const durationDiv = document.getElementById('duration');
const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const speedUpBtn = document.getElementById('speedUpBtn');
const speedDownBtn = document.getElementById('speedDownBtn');
const speedSlider = document.getElementById('speedSlider');
const sliderValue = document.getElementById('sliderValue');
const statusChip = document.getElementById('statusChip');
const loadingOverlay = document.getElementById('loadingOverlay');
const countdownOverlay = document.getElementById('countdownOverlay');
const countdownNumber = document.getElementById('countdownNumber');
const historyTableBody = document.getElementById('historyTableBody');
const importHistoryBtn = document.getElementById('importHistoryBtn');
const exportHistoryBtn = document.getElementById('exportHistoryBtn');
const importHistoryInput = document.getElementById('importHistoryInput');
const snackbar = document.getElementById('snackbar');
const prepareNotionBtn = document.getElementById('prepareNotionBtn');
const downloadNotionBtn = document.getElementById('downloadNotionBtn');
const notionPreview = document.getElementById('notionPreview');
const recoveryNotice = document.getElementById('recoveryNotice');
const continueWalkBtn = document.getElementById('continueWalkBtn');
const newWalkRecordBtn = document.getElementById('newWalkRecordBtn');
const buildNotionExport = PitPatWalks.buildNotionExport;
const safetyStatus = document.getElementById('safetyStatus');
let preparedNotionExport = null;
let selectedTransport = null;
let transportReady = Promise.resolve();
let bridgeStopPromise = null;
let bridgeStopDisconnect = false;
let bridgeSnapshot = null;
let sharedWalks = [];
let sharedHistoryError = null;
let sharedRefresh = null;
let sharedRefreshAgain = false;
let sharedRefreshTimer = null;
let historyModePending = typeof PitPatTransports !== 'undefined' && typeof fetch === 'function';
const sharedRecording = () => selectedTransport?.kind === 'bridge' && selectedTransport.recording === 'bridge';
const ownsMotion = () => !selectedTransport?.observers || bridgeSnapshot?.is_owner === true;

function loadSessions() {
    if (sharedHistoryError) throw Error(sharedHistoryError);
    return sharedRecording() ? PitPatWalks.combineHistories(loadLocalSessions(), sharedWalks) : loadLocalSessions();
}
function historyError(error) {
    sharedHistoryError = error.message;
    const label = document.getElementById('historyStatus');
    if (label) label.textContent = 'Shared history unavailable: ' + error.message;
    preparedNotionExport = null;
    downloadNotionBtn.disabled = true;
}
async function refreshSharedHistory() {
    if (!sharedRecording() || typeof selectedTransport.walks !== 'function') return;
    if (sharedRefresh) { sharedRefreshAgain = true; return sharedRefresh; }
    sharedRefresh = (async () => {
        const rows = []; let before;
        do {
            const page = await selectedTransport.walks({limit:100,before});
            if (!Array.isArray(page.walks)) throw Error('Invalid shared history response');
            rows.push(...page.walks); before = page.next_cursor;
        } while (before);
        // Validate conflicts before publishing any part of the fetched history.
        PitPatWalks.combineHistories(loadLocalSessions(), rows);
        sharedWalks = rows; sharedHistoryError = null;
        const label = document.getElementById('historyStatus');
        if (label) label.textContent = 'Bridge walks and preserved browser history. Shared records cannot be deleted here.';
        renderSessionTable();
    })().catch(historyError).finally(() => {
        sharedRefresh = null;
        if (sharedRefreshAgain) { sharedRefreshAgain = false; return refreshSharedHistory(); }
    });
    return sharedRefresh;
}
function scheduleHistoryRefresh() {
    if (!sharedRefreshTimer) sharedRefreshTimer = setTimeout(() => { sharedRefreshTimer = null; refreshSharedHistory(); }, 250);
}
function applyBridgeSnapshot(view) {
    if (!view) return;
    const lostOwnership = bridgeSnapshot?.is_owner && !view.is_owner;
    bridgeSnapshot = view;
    if (lostOwnership) { motionGeneration++; pendingData = null; }
    if (view.connected && !connected) {
        connected = true; connectionEpoch++; writeChar = {bridge:true}; notifyChar = {};
        connectBtn.textContent = 'Stop & Disconnect';
    }
    motionBlocked = view.blocked || view.stale || !!view.storage_fault || !!view.fault_id;
    const ack = document.getElementById('acknowledgeRecoveryBtn');
    if (ack) { ack.hidden = !view.fault_id; ack.disabled = !view.is_recovery_claimant || view.session?.status === 'interrupted'; }
    if (view.fault_id) safetyMessage((view.safety_fault?.reason || 'Safety fault') + '. Explicit recovery required.');
    const ownerLabel = document.getElementById('ownerStatus');
    if (ownerLabel) ownerLabel.textContent = view.is_owner ? 'This browser controls motion' :
        (view.owner_kind ? view.owner_kind + ' controls motion — this browser observes' : 'No motion controller');
    const take = document.getElementById('takeControlBtn');
    if (take) {
        take.hidden = !view.connected || view.is_owner;
        take.disabled = motionBlocked || view.stopping || view.recovery;
    }
    if (view.is_owner && !lostOwnership && view.target_speed && curTargetSpeed !== view.target_speed) {
        curTargetSpeed = view.target_speed; syncTargetSpeed();
    }
    if (sharedRecording()) recoveryNotice.hidden = view.session?.status !== 'interrupted';
    if (view.storage_fault) historyError(Error(view.storage_fault));
    updateRunningState(runningState);
}

// --- Session History Logic ---
let sessionActive = false;
let sessionStartData = null;
let lastSession = null;

const KM_PER_MILE = 1.609344;
const HISTORY_BACKUP_KEY = 'treadmill_sessions_backup_v1';

function speedInMph(value, unit) {
    const speed = Number(value);
    if (!Number.isFinite(speed) || value === null || value === '') return null;
    if (unit === 'mph') return speed;
    if (unit === 'kph' || unit === 'km/h') return speed / KM_PER_MILE;
    return null; // Never guess units for an imported record.
}

function americanSession(session) { return PitPatWalks.normalizeSession(session); }

// Back up the exact original JSON before any migration or history write.
// If storage is full/unavailable this throws before replacing the history.
function backupHistory() {
    const original = localStorage.getItem('treadmill_sessions');
    if (original !== null && localStorage.getItem(HISTORY_BACKUP_KEY) === null) {
        localStorage.setItem(HISTORY_BACKUP_KEY, original);
    }
}

function loadLocalSessions() {
    let sessions = [];
    try {
        sessions = JSON.parse(localStorage.getItem('treadmill_sessions') || '[]');
    } catch {}
    if (!Array.isArray(sessions)) return [];
    const normalized = PitPatWalks.identify(sessions.map(americanSession));
    if (!historyModePending && !sharedRecording() && JSON.stringify(normalized) !== JSON.stringify(sessions)) {
        try {
            saveSessions(normalized);
        } catch (err) {
            console.error('History migration was not saved; original history retained.', err);
        }
    }
    return normalized;
}
function saveSessions(sessions) {
    backupHistory();
    localStorage.setItem('treadmill_sessions', JSON.stringify(PitPatWalks.identify(sessions.map(americanSession))));
    if (preparedNotionExport) {
        preparedNotionExport = null;
        downloadNotionBtn.disabled = true;
        notionPreview.textContent = 'History changed. Choose Prepare for Notion again for a fresh preview.';
    }
}
function addSession(session) {
    const sessions = loadLocalSessions();
    sessions.unshift(session); // newest first
    saveSessions(sessions);
    renderSessionTable();
}
function deleteSession(idx) {
    const sessions = loadLocalSessions();
    if (sessions[idx]?.sessionId === sessionStartData?.sessionId) {
        showToast('Finish or resolve the current walk before deleting its record.');
        return;
    }
    sessions.splice(idx, 1);
    saveSessions(sessions);
    renderSessionTable();
}
function renderSessionTable() {
    let sessions;
    try { sessions = loadSessions(); } catch (error) { historyError(error); return; }
    historyTableBody.innerHTML = '';
    sessions.forEach((s, i) => {
        if (!s || typeof s !== 'object' || Array.isArray(s)) return;
        let avgSpeedDisplay = '-';
        if (typeof s.avgSpeed === 'number' && !isNaN(s.avgSpeed)) {
            avgSpeedDisplay = s.avgSpeed.toFixed(2) + ' ' + (s.speedUnit || '');
        } else if (typeof s.avgSpeed === 'string' && !isNaN(parseFloat(s.avgSpeed))) {
            avgSpeedDisplay = parseFloat(s.avgSpeed).toFixed(2) + ' ' + (s.speedUnit || '');
        }
        let dateStr = '-';
        if (typeof s.date === 'number' || typeof s.date === 'string') {
            dateStr = Number.isFinite(new Date(s.date).getTime()) ? PitPatWalks.eastern(s.date) : '-';
        }
        const tr = document.createElement('tr');
        const distance = PitPatWalks.distanceMiles(s);
        const values = [dateStr, Number.isFinite(s.duration) ? formatDuration(s.duration) : '-',
            s.steps ?? '-', s.calories ?? '-', distance === null ? '-' : distance.toFixed(3) + ' mi',
            s.status || 'legacy', avgSpeedDisplay];
        for (const value of values) {
            const cell = document.createElement('td');
            cell.textContent = String(value);
            tr.appendChild(cell);
        }
        const action = document.createElement('td');
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.textContent = 'Delete';
        const shared = sharedRecording() && sharedWalks.some(row => row.sessionId === s.sessionId);
        remove.disabled = shared;
        remove.textContent = shared ? 'Shared record' : 'Delete';
        remove.addEventListener('click', () => {
            if (shared) return;
            const localIndex = loadLocalSessions().findIndex(row => row.sessionId === s.sessionId);
            if (localIndex >= 0) deleteSession(localIndex);
        });
        action.appendChild(remove);
        tr.appendChild(action);
        historyTableBody.appendChild(tr);
    });
}
window.deleteSessionFromTable = deleteSession;

// --- State ---
let device = null;
let server = null;
let notifyChar = null;
let writeChar = null;
let treadmillData = {};
let connected = false;
let runningState = 3; // 0: Starting, 1: Running, 2: Paused, 3: Stopped
let curTargetSpeed = 1000; // in treadmill units
let connectionEpoch = 0;
let motionGeneration = 0;
let writeTail = Promise.resolve();
let notificationSequence = 0;
let stopping = false;
let disconnectInProgress = false;
let motionBlocked = false;
let stopRequest = null;
let expectedDisconnect = false;

function safetyMessage(message) {
    safetyStatus.textContent = message;
    safetyStatus.hidden = !message;
}

// Serialize GATT writes. Old queued motion is cancelled when Stop is requested,
// and no queued operation can cross a lost/replaced connection.
function writeBluetooth(packet, beforeWrite) {
    const epoch = connectionEpoch;
    const generation = motionGeneration;
    const characteristic = writeChar;
    const isMotion = packet.length === 23 && packet[12] !== 0;
    const operation = writeTail.then(async () => {
        if (!connected || epoch !== connectionEpoch || characteristic !== writeChar) return false;
        if (isMotion && (generation !== motionGeneration || stopping || motionBlocked || disconnectInProgress)) return false;
        if (packet.length !== 23 && stopping && stopRequest?.minSequence === null) return false;
        if (!characteristic) throw new Error('Bluetooth write characteristic is unavailable.');
        if (beforeWrite) beforeWrite();
        await characteristic.writeValue(packet);
        return true;
    });
    writeTail = operation.catch(() => {});
    return operation;
}

function requestStop() {
    if (selectedTransport?.kind === 'bridge') return requestBridgeStop(false);
    if (stopRequest) return stopRequest.promise;
    pendingData = null;
    motionGeneration++;
    motionBlocked = true;
    if (!connected || !writeChar) {
        safetyMessage('Stop unconfirmed. The belt may still be moving. Use the physical stop control.');
        return Promise.resolve(false);
    }
    stopping = true;
    updateRunningState(runningState);
    safetyMessage('Stop requested. Waiting for a fresh stopped, zero-speed report.');
    const request = { epoch: connectionEpoch, minSequence: null, confirmed: false };
    let resolveReport;
    const report = new Promise(resolve => { resolveReport = resolve; });
    request.resolve = resolveReport;
    // Timeout/loss must cancel the WHOLE operation even if telemetry resolved
    // before the GATT write promise, or the browser could wait forever.
    const cancelled = new Promise((resolve, reject) => {
        request.reject = reject;
        request.timer = setTimeout(() => reject(new Error('Stop confirmation timed out.')), 5000);
    });
    stopRequest = request;
    const write = writeBluetooth(makePacket('stop'), () => { request.minSequence = notificationSequence; });
    request.promise = Promise.race([Promise.all([write, report]), cancelled]).then(([written]) => {
        if (!written || request.epoch !== connectionEpoch || !connected) throw new Error('Connection lost during Stop.');
        if (!request.confirmed || runningState !== 3 || treadmillData._raw?.current_speed !== 0) throw new Error('Latest telemetry does not confirm Stop.');
        motionBlocked = false;
        safetyMessage('Treadmill reported stopped with zero speed.');
        return true;
    }).catch(err => {
        motionBlocked = true;
        pendingData = null;
        console.error('Stop unconfirmed:', err);
        safetyMessage('Stop unconfirmed. Use the physical stop control. Bluetooth is kept open if still available.');
        return false;
    }).finally(() => {
        clearTimeout(request.timer);
        if (stopRequest === request) {
            stopRequest = null;
            stopping = false;
            updateRunningState(runningState);
        }
    });
    return request.promise;
}

function syncTargetSpeed() {
    const mph = (curTargetSpeed / 1000 / KM_PER_MILE).toFixed(2);
    speedSlider.value = mph;
    sliderValue.textContent = mph;
    if (speedSlider.MaterialSlider) speedSlider.MaterialSlider.change(mph);
}

function setTargetMph(value) {
    const mph = Number(value);
    if (!Number.isFinite(mph) || value === '') {
        syncTargetSpeed();
        return;
    }
    // Commands remain metric: nearest 0.1 kph, clamped AFTER rounding.
    curTargetSpeed = Math.max(1000, Math.min(6000, Math.round(mph * KM_PER_MILE * 10) * 100));
    syncTargetSpeed();
    send_data(makePacket('set_speed', curTargetSpeed));
}

// --- Helper Functions ---

function setStatus(msg) {
    let displayMsg = msg;
    if (msg.toLowerCase().includes('connecting')) {
        displayMsg = 'Connecting';
    } else if (msg.toLowerCase().includes('not connected') || msg.toLowerCase().includes('disconnect')) {
        displayMsg = 'Disconnected';
    } else if (msg.toLowerCase().includes('paused')) {
        displayMsg = 'Paused';
    } else if (msg.toLowerCase().includes('running')) {
        displayMsg = 'Running';
    } else if (msg.toLowerCase().includes('stopped')) {
        displayMsg = 'Stopped';
    }
    if (statusChip) {
        statusChip.querySelector('.mdl-chip__text').textContent = displayMsg;
        statusChip.classList.remove('chip-connected', 'chip-connecting', 'chip-disconnected', 'chip-paused');
        if (displayMsg === 'Running') {
            statusChip.classList.add('chip-connected');
        } else if (displayMsg === 'Connecting') {
            statusChip.classList.add('chip-connecting');
        } else if (displayMsg === 'Paused') {
            statusChip.classList.add('chip-paused');
        } else {
            statusChip.classList.add('chip-disconnected');
        }
    }
}
function updateDashboard(data) {
    speedDiv.textContent = data.speed || '-';
    distanceDiv.textContent = data.distance || '-';
    caloriesDiv.textContent = data.calories || '-';
    stepsDiv.textContent = (data.steps !== undefined && data.steps !== null) ? data.steps : '-';
    if (typeof data.duration === 'number') {
        durationDiv.textContent = formatDuration(data.duration);
    } else if (typeof data.duration === 'string' && !isNaN(parseFloat(data.duration))) {
        durationDiv.textContent = formatDuration(parseFloat(data.duration));
    } else {
        durationDiv.textContent = data.duration || '-';
    }
}
function enableControls(enable) {
    const bridgeBlocked = selectedTransport?.observers && (!bridgeSnapshot || bridgeSnapshot.blocked || bridgeSnapshot.stale || bridgeSnapshot.storage_fault || bridgeSnapshot.session?.status === 'interrupted');
    const allowMotion = enable && ownsMotion() && !bridgeBlocked && !stopping && !disconnectInProgress && !motionBlocked;
    startBtn.disabled = !allowMotion;
    stopBtn.disabled = !connected || !writeChar;
    speedUpBtn.disabled = !allowMotion;
    speedDownBtn.disabled = !allowMotion;
    speedSlider.disabled = !allowMotion;
}
function updateRunningState(state) {
    runningState = state;
    if (!connected) {
        enableControls(false);
        startBtn.textContent = "Start";
        setStatus('Disconnected');
    } else {
        switch (state) {
            case 0: // Starting
                enableControls(false);
                startBtn.textContent = "Start";
                setStatus('Starting');
                break;
            case 1: // Running
                enableControls(true);
                startBtn.textContent = "Pause";
                setStatus('Running');
                break;
            case 2: // Paused
                enableControls(true);
                startBtn.textContent = "Start";
                setStatus('Paused');
                break;
            case 3: // Stopped
                enableControls(true);
                startBtn.textContent = "Start";
                setStatus('Stopped');
                break;
            default:
                enableControls(false);
                startBtn.textContent = "Start";
                setStatus('Connected — telemetry unavailable (readings stale)');
        }
    }
}
function formatDuration(seconds) {
    seconds = Math.floor(seconds);
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    let parts = [];
    if (h > 0) parts.push(h + 'h');
    if (m > 0 || h > 0) parts.push(m + 'm');
    parts.push(s + 's');
    return parts.join(' ');
}

// --- Send Data Logic (replaces sendCommand) ---
let pendingData = null;
function send_data(packet) {
    if (!ownsMotion() || stopping || disconnectInProgress || motionBlocked) return;
    if (selectedTransport?.kind === 'bridge') {
        const op = packet[12] === 0 ? 'stop' : packet[12] === 2 ? 'pause' : packet[8] === 5 ? 'set_speed' : 'start';
        const epoch = connectionEpoch;
        const transport = selectedTransport;
        const generation = motionGeneration;
        selectedTransport.command(op, {speed: packet[6] * 256 + packet[7]}).catch(err => {
            if (!connected || epoch !== connectionEpoch || generation !== motionGeneration || transport !== selectedTransport) return;
            motionBlocked = true;
            updateRunningState(null);
            safetyMessage(err.message + '. Belt state is unconfirmed; use the physical stop control if needed.');
        });
        return;
    }
    pendingData = packet;
}

// --- Bluetooth Logic ---
function bindBridgeTransport(transport) {
    transport.onEvent(event => {
        const data = event.data || {};
        if (event.snapshot) applyBridgeSnapshot(event.snapshot);
        if (event.event === 'snapshot') {
            if (event.snapshot?.telemetry) {
                const hex = event.snapshot.telemetry;
                if (/^(?:[0-9a-f]{2}){31,255}$/i.test(hex) && notifyChar) {
                    const bytes = Uint8Array.from(hex.match(/../g), v=>parseInt(v,16));
                    notifyChar.value = new DataView(bytes.buffer); handleNotification({target:notifyChar});
                }
            }
            return;
        }
        if (event.event === 'walk') { scheduleHistoryRefresh(); return; }
        if (event.event === 'storage_fault') { historyError(Error(data.message)); return; }
        if (event.event === 'state') {
            if (data.state === 'stopping') motionGeneration++;
            if (data.connected && !connected) {
                connectionEpoch++;
                connected = true;
                writeChar = {bridge:true};
                notifyChar = {};
                connectBtn.textContent = 'Stop & Disconnect';
            }
            motionBlocked = data.blocked !== false;
            if (data.connected) updateRunningState(motionBlocked ? null : runningState);
        } else if (event.event === 'telemetry') {
            if (!connected || !notifyChar || !/^(?:[0-9a-f]{2}){31,255}$/i.test(data.hex || '')) return;
            const bytes = Uint8Array.from(data.hex.match(/../g), value => parseInt(value, 16));
            notifyChar.value = new DataView(bytes.buffer);
            handleNotification({target:notifyChar});
        } else if (event.event === 'safety') {
            safetyMessage(data.message);
            if (!data.confirmed) { motionBlocked = true; updateRunningState(null); }
        } else if (event.event === 'disconnected') {
            expectedDisconnect = data.confirmed === true;
            onDisconnected();
        } else if (event.event === 'lost') {
            if (connected) onDisconnected();
            else showToast(data.message || 'Local bridge unavailable.');
        }
    });
}

async function requestBridgeStop(disconnect) {
    if (bridgeStopPromise) {
        if (disconnect && !bridgeStopDisconnect) return bridgeStopPromise.then(confirmed => confirmed ? requestBridgeStop(true) : false);
        return bridgeStopPromise;
    }
    bridgeStopDisconnect = disconnect;
    stopping = true;
    disconnectInProgress = disconnect;
    motionBlocked = true;
    pendingData = null;
    motionGeneration++;
    connectBtn.disabled = disconnect;
    updateRunningState(runningState);
    safetyMessage('Stop requested. Waiting for a fresh stopped, zero-speed report.');
    bridgeStopPromise = (async () => {
        try {
            const result = await (disconnect ? selectedTransport.stopDisconnect() : selectedTransport.stop());
            if (!result.confirmed) throw Error('Stop unconfirmed. Use the physical stop control. Bluetooth is kept open if available.');
            motionBlocked = !connected;
            if (connected) safetyMessage('Treadmill reported stopped with zero speed.');
            return true;
        } catch (error) {
            safetyMessage(error.message);
            return false;
        } finally {
            stopping = disconnectInProgress = false;
            connectBtn.disabled = false;
            bridgeStopPromise = null;
            bridgeStopDisconnect = false;
            updateRunningState(runningState);
        }
    })();
    return bridgeStopPromise;
}

async function connectBridge(recover = false) {
    connectBtn.disabled = true;
    try {
        let id = null;
        if (!recover) {
            const devices = await selectedTransport.discover();
            if (!devices.length) throw Error('No PitPat treadmill found. Check Bluetooth and treadmill power.');
            id = await PitPatUI.chooseDevice(devices);
            if (!id) return;
        }
        await selectedTransport.connect(id, recover);
    } catch (error) {
        safetyMessage(error.message);
    } finally {
        connectBtn.disabled = false;
    }
}

async function connectBluetooth() {
    await transportReady;
    if (selectedTransport?.kind === 'bridge') return connectBridge();
    if (!navigator.bluetooth?.requestDevice) {
        safetyMessage('This browser needs the local PitPat bridge. Start the bridge and open its dashboard URL.');
        return;
    }
    connectionEpoch++;
    pendingData = null;
    writeTail = Promise.resolve();
    expectedDisconnect = false;
    setStatus('Connecting');
    if (loadingOverlay) loadingOverlay.style.display = 'flex';
    try {
        console.log("Requesting Bluetooth device...");
        device = await navigator.bluetooth.requestDevice({
            filters: [{ services: [SERVICE_UUID] }],
            services: [SERVICE_UUID]
        });
        console.log("Device selected:", device);
        setStatus('Connecting');
        device.addEventListener('gattserverdisconnected', onDisconnected);
        server = await device.gatt.connect();
        console.log("GATT server connected:", server);
        let services = await server.getPrimaryServices();
        console.log("Primary services:", services.map(s => s.uuid));
        notifyChar = await server.getPrimaryService(SERVICE_UUID).then(
            service => service.getCharacteristic(NOTIFY_CHAR_UUID)
        ).catch(async () => {
            // fallback: try to find the service by iterating
            let services = await server.getPrimaryServices();
            for (let s of services) {
                try {
                    let c = await s.getCharacteristic(NOTIFY_CHAR_UUID);
                    if (c) return c;
                } catch {}
            }
            throw new Error("Notify characteristic not found");
        });
        console.log("Notify characteristic:", notifyChar);
        writeChar = await server.getPrimaryService(SERVICE_UUID).then(
            service => service.getCharacteristic(WRITE_CHAR_UUID)
        ).catch(async () => {
            let services = await server.getPrimaryServices();
            for (let s of services) {
                try {
                    let c = await s.getCharacteristic(WRITE_CHAR_UUID);
                    if (c) return c;
                } catch {}
            }
            throw new Error("Write characteristic not found");
        });
        console.log("Write characteristic:", writeChar);
        await notifyChar.startNotifications();
        notifyChar.addEventListener('characteristicvaluechanged', handleNotification);
        connected = true;
        motionBlocked = true;
        connectBtn.textContent = "Stop & Disconnect";
        updateRunningState(null);
        setStatus('Awaiting telemetry');
        safetyMessage('Connected; waiting for fresh treadmill state. Stop is available.');
        // No heartbeat loop, just send heartbeat or data on notification
        if (loadingOverlay) loadingOverlay.style.display = 'none';
    } catch (err) {
        console.error("Bluetooth connection error:", err);
        showToast("Bluetooth error: " + err);
        setStatus('Disconnected');
        connected = false;
        connectBtn.textContent = "Connect";
        if (loadingOverlay) loadingOverlay.style.display = 'none';
        // stopHeartbeatLoop();
    }
}

async function disconnectBluetooth() {
    if (selectedTransport?.kind === 'bridge') return requestBridgeStop(true);
    if (disconnectInProgress) return false;
    disconnectInProgress = true;
    connectBtn.disabled = true;
    try {
        const epoch = connectionEpoch;
        const stopped = await requestStop();
        if (!stopped || epoch !== connectionEpoch || !connected) return false;
        expectedDisconnect = true;
        if (device?.gatt.connected) device.gatt.disconnect();
        // Some implementations deliver the disconnection event asynchronously.
        if (connected) onDisconnected();
        return true;
    } finally {
        disconnectInProgress = false;
        connectBtn.disabled = false;
        if (connected) updateRunningState(runningState);
    }
}

function onDisconnected(event) {
    if (event?.target && event.target !== device) return;
    if (event && !connected && !writeChar) return; // Ignore a duplicate GATT event after our cleanup.
    const confirmed = expectedDisconnect;
    expectedDisconnect = false;
    connectionEpoch++;
    motionGeneration++;
    pendingData = null;
    motionBlocked = true;
    if (stopRequest) stopRequest.reject(new Error('Bluetooth connection lost.'));
    writeChar = null;
    notifyChar = null;
    writeTail = Promise.resolve();
    connected = false;
    setStatus('Disconnected');
    connectBtn.textContent = "Connect";
    updateRunningState(null);
    safetyMessage(confirmed ? 'Stopped confirmed before Bluetooth disconnected.' :
        'Connection lost. The belt may still be moving. Use the physical stop control; automatic stop is unconfirmed.');
    if (sessionActive && sessionStartData) {
        sessionStartData.stopConfirmed = false;
        try { finishSession('Disconnected'); }
        catch (err) { console.error('Could not save interrupted walk.', err); }
    }
}

function handleNotification(event) {
    if (notifyChar && event.target !== notifyChar) return;
    const value = event.target.value;
    notificationSequence++;
    // Logging for debugging
    console.log("Received notification, byteLength:", value.byteLength);
    let hexStr = [];
    for (let i = 0; i < value.byteLength; ++i) {
        hexStr.push(value.getUint8(i).toString(16).padStart(2, "0"));
    }
    console.log("Payload (hex):", hexStr.join(" "));
    // Parse treadmill data from value (see treadmill_data.py for structure)
    let raw;
    try {
        raw = PitPatProtocol.parseTelemetry(new Uint8Array(value.buffer, value.byteOffset, value.byteLength));
    } catch (err) {
        motionBlocked = true;
        updateRunningState(null);
        safetyMessage('Invalid treadmill telemetry. Displayed readings are stale. Stop cannot be confirmed. Use the physical stop control if the belt is moving.');
        if (sessionActive && sessionStartData) finishSession('Disconnected');
        return;
    }
    const {current_speed, distance, calories, steps, duration, flags, running_state, speed_unit, distance_unit} = raw;
    const unit_mode = speed_unit === 'mph' ? 1 : 0;
    const statusArr = ["Starting", "Running", "Paused", "Stopped"];
    const mph = speedInMph(current_speed / 1000, speed_unit);
    treadmillData = {
        speed: mph.toFixed(2) + " mph",
        distance: (distance / 1000 / (unit_mode === 1 ? 1 : KM_PER_MILE)).toFixed(2) + " mi",
        calories: calories + " Cal",
        steps: steps,
        duration: Math.round(duration / 1000),
        status: statusArr[running_state] || "Unknown",
        _raw: { current_speed, distance, calories, steps, duration, speed_unit, distance_unit,
            flags, running_state, packetHex: hexStr.join('') }
    };
    // Log parsed fields
    console.log("Parsed treadmill data:", treadmillData);
    updateDashboard(treadmillData);
    // A GATT write acknowledgement is not evidence that the belt has stopped.
    // Require fresh telemetry AFTER the stop write began, with BOTH conditions.
    if (running_state === 3 && current_speed === 0) {
        motionBlocked = selectedTransport?.kind === 'bridge' ? !!(bridgeSnapshot?.blocked || bridgeSnapshot?.fault_id || bridgeSnapshot?.stale) : false;
        if (stopRequest && stopRequest.epoch === connectionEpoch &&
            stopRequest.minSequence !== null && notificationSequence > stopRequest.minSequence) {
            stopRequest.confirmed = true;
            stopRequest.resolve();
        }
        if (!stopRequest && connected && !bridgeSnapshot?.fault_id) safetyMessage('Treadmill reported stopped with zero speed.');
    } else if (!stopping && !stopRequest && !motionBlocked && connected) {
        safetyMessage(running_state === 3 ?
            'Treadmill still reports movement; stopped state is unconfirmed.' :
            'Treadmill reports ' + statusArr[running_state].toLowerCase() + '.');
    }
    // Stopped flags can precede the end of deceleration. Keep tracking until
    // both state and measured speed confirm Stop.
    const trackingState = running_state === 3 && current_speed !== 0 ? 0 : running_state;
    updateRunningState(trackingState);
    if (trackingState === 0 && running_state === 3) setStatus('Stopping');

    // Storage/render failures must not prevent the Bluetooth heartbeat.
    try {
        if (!sharedRecording()) captureWalk(trackingState, treadmillData._raw, mph);
    } catch (err) {
        console.error('Walk could not be saved.', err);
        showToast('Walk saving failed. Export history and check browser storage.');
    }

    // Consume the pending command before writing: completion of an older write
    // must not erase a newer command. Stop uses the same serialized writer directly.
    if (writeChar && connected && selectedTransport?.kind !== 'bridge') {
        const packet = pendingData || new Uint8Array([0x6a, 0x05, 0xfd, 0xf8, 0x43]);
        const epoch = connectionEpoch;
        const characteristic = writeChar;
        pendingData = null;
        writeBluetooth(packet).catch(err => {
            // An in-flight heartbeat may reject after an intentional disconnect.
            // Its stale error must not replace that outcome or a new connection.
            if (!connected || epoch !== connectionEpoch || characteristic !== writeChar) return;
            console.error('Bluetooth write failed:', err);
            safetyMessage('Bluetooth command failed; belt state is unconfirmed. Use the physical stop control if needed.');
        });
    }
}

// --- Command Packet Generators (see treadmill_controller.py) ---
/**
 * Constructs a treadmill command packet.
 * @param {string} type - Command type: "start", "pause", "stop", or "set_speed".
 * @param {number} [speed=1000] - Target speed in treadmill units (integer, 1000 = 1.00 kph, range: 1000 to 6000).
 * @returns {Uint8Array} The command packet.
 */
function makePacket(type, speed = 1000) {
    return PitPatProtocol.makePacket(type, speed);
}

// --- UI Event Handlers ---
connectBtn.addEventListener('click', async () => {
    if (!connected) return connectBluetooth();
    return disconnectBluetooth();
});

startBtn.addEventListener('click', async () => {
    if (!connected || stopping || disconnectInProgress || motionBlocked) return;
    if (runningState === 1) { // Running -> Pause
        send_data(makePacket("pause"));
    } else { // Start
        // Show countdown overlay (visual only, do not delay command)
        if (countdownOverlay && countdownNumber) {
            countdownOverlay.style.display = 'flex';
            countdownOverlay.style.opacity = '1';
            let count = 3;
            countdownNumber.textContent = count;
            countdownNumber.style.opacity = '1';
            countdownNumber.style.transform = 'scale(1)';
            // Animate countdown in background
            (async () => {
                for (let i = 0; i < 3; i++) {
                    await new Promise(res => setTimeout(res, 700));
                    countdownNumber.style.transform = 'scale(1.3)';
                    countdownNumber.style.opacity = '0.5';
                    await new Promise(res => setTimeout(res, 200));
                    count--;
                    if (count > 0) {
                        countdownNumber.textContent = count;
                        countdownNumber.style.opacity = '1';
                        countdownNumber.style.transform = 'scale(1)';
                    }
                }
                await new Promise(res => setTimeout(res, 400));
                countdownOverlay.style.opacity = '0';
                await new Promise(res => setTimeout(res, 500)); // Wait for fade-out
                countdownOverlay.style.display = 'none';
                countdownOverlay.style.opacity = '1'; // Reset for next time
            })();
        }
        send_data(makePacket("start", curTargetSpeed));
    }
});

stopBtn.addEventListener('click', () => requestStop());

speedUpBtn.addEventListener('click', () => {
    if (!connected || !ownsMotion()) return;
    setTargetMph(curTargetSpeed / 1000 / KM_PER_MILE + 0.1);
});

speedDownBtn.addEventListener('click', () => {
    if (!connected || !ownsMotion()) return;
    setTargetMph(curTargetSpeed / 1000 / KM_PER_MILE - 0.1);
});

speedSlider.addEventListener('input', () => {
    sliderValue.textContent = speedSlider.value;
});
speedSlider.addEventListener('change', () => {
    if (!connected || !ownsMotion()) return;
    setTargetMph(speedSlider.value);
});

// --- Initialize ---
updateDashboard({});
updateRunningState(3);
syncTargetSpeed();
renderSessionTable();

function saveCurrentSession(session) {
    localStorage.setItem('treadmill_current_session', JSON.stringify(session));
}
function loadCurrentSession() {
    try {
        return JSON.parse(localStorage.getItem('treadmill_current_session')) || null;
    } catch { return null; }
}
function clearCurrentSession() {
    localStorage.removeItem('treadmill_current_session');
}

function upsertLiveSession(session) {
    const sessions = loadLocalSessions();
    const index = sessions.findIndex(s => s && s.sessionId === session.sessionId);
    if (index >= 0) sessions[index] = session;
    else sessions.unshift(session);
    saveSessions(sessions);
    renderSessionTable();
}

function persistWalk() {
    if (!sessionStartData) return;
    const walk = sessionStartData;
    walk.avgSpeed = walk.speedCount > 0 ? walk.speedSum / walk.speedCount / 1000 : null;
    walk.observedElapsedSeconds = Math.max(0, (walk.lastObservedAt - walk.date) / 1000);
    upsertLiveSession({ ...walk });
    saveCurrentSession(walk);
}

function captureWalk(state, raw, mph) {
    if (sessionStartData?.status === 'interrupted') return; // User decides how to reconcile reconnects.
    const now = Date.now();
    const miles = raw.distance / 1000 / (raw.distance_unit === 'mi' ? 1 : KM_PER_MILE);
    const counters = { duration: raw.duration / 1000, steps: raw.steps, calories: raw.calories, distanceMiles: miles };
    const previous = sessionStartData?.lastCounters;
    const reset = previous && Object.keys(counters).some(k => counters[k] + 0.00001 < previous[k]);
    if (reset) {
        // A reset notification must never erase the last nonzero totals.
        sessionStartData.coverage = 'partial';
        finishSession(state === 3 ? 'Stopped (counters reset)' : 'Counter reset');
        if (state !== 1) return;
    }
    if (!sessionStartData) {
        if (state !== 1) return;
        sessionStartData = {
            schemaVersion: 2, trackingVersion: 1, sessionId: PitPatWalks.id(),
            date: now, startedAt: new Date(now).toISOString(), startBasis: 'First running observation',
            coverage: raw.duration <= 2000 && raw.steps === 0 && raw.distance === 0 && raw.calories === 0 ? 'complete' : 'partial',
            speedSum: 0, speedCount: 0, speedUnit: 'mph', maxSpeedMph: 0,
            activeDurationSeconds: null, speedSamples: [],
        };
        if (localStorage.getItem('treadmill_new_record_pending') === '1') {
            sessionStartData.counterBaseline = { ...counters };
            sessionStartData.coverage = 'partial';
            sessionStartData.startBasis = 'First observation after an explicit new-record boundary; counters are deltas from this point';
        }
        sessionActive = true;
    }
    const walk = sessionStartData;
    walk.status = state === 2 ? 'paused' : state === 3 ? 'completed' : state === 0 ? 'starting' : 'running';
    walk.lastObservedAt = now;
    walk.lastCounters = counters;
    const baseline = walk.counterBaseline || { duration: 0, steps: 0, calories: 0, distanceMiles: 0 };
    walk.duration = counters.duration - baseline.duration;
    walk.steps = counters.steps - baseline.steps;
    walk.calories = (counters.calories - baseline.calories) + ' Cal';
    walk.distanceMiles = miles - baseline.distanceMiles;
    walk.sourceTelemetry = { ...raw };
    walk.speedSamples ||= [];
    if (state === 1) {
        walk.speedSum += mph * 1000;
        walk.speedCount += 1;
        walk.maxSpeedMph = Math.max(walk.maxSpeedMph || 0, mph);
        // Keep a compact sampled trace, with every notification included in sum/max.
        if (!walk.speedSamples.length || now - walk.speedSamples.at(-1).at >= 5000) {
            walk.speedSamples.push({ at: now, mph, sourceSpeed: raw.current_speed, sourceUnit: raw.speed_unit });
        }
    }
    if (state === 3) finishSession('Stopped');
    else persistWalk();
    localStorage.removeItem('treadmill_new_record_pending');
}

function finishSession(reason) {
    if (!sessionStartData) return;
    const interrupted = !reason.startsWith('Stopped');
    sessionStartData.status = interrupted ? 'interrupted' : 'completed';
    sessionStartData.endReason = reason;
    sessionStartData.endedAt = new Date(sessionStartData.lastObservedAt || sessionStartData.date).toISOString();
    if (interrupted) sessionStartData.coverage = 'partial';
    persistWalk();
    if (interrupted && reason !== 'Counter reset') {
        recoveryNotice.hidden = false;
        return;
    }
    sessionActive = false;
    sessionStartData = null;
    clearCurrentSession();
    recoveryNotice.hidden = true;
}

// Recovery never starts the belt or silently joins unrelated workouts.
function initializeLocalRecovery() {
const restored = loadCurrentSession();
if (restored) {
    sessionActive = true;
    sessionStartData = restored;
    const prior = loadLocalSessions().find(s => s && s.date === restored.date);
    sessionStartData.sessionId ||= prior?.sessionId || PitPatWalks.id();
    if (['kph', 'km/h'].includes(sessionStartData.speedUnit)) sessionStartData.speedSum /= KM_PER_MILE;
    sessionStartData.speedUnit = 'mph';
    sessionStartData.speedSum ||= 0;
    sessionStartData.speedCount ||= 0;
    sessionStartData.coverage = 'partial';
    finishSession('Page reloaded; continuity needs review');
}
}
if (!historyModePending) initializeLocalRecovery();
continueWalkBtn.addEventListener('click', () => {
    if (sharedRecording()) {
        selectedTransport.resolveSession(bridgeSnapshot?.session?.sessionId, 'continue').then(()=>refreshSharedHistory()).catch(historyError); return;
    }
    if (!sessionStartData || !connected) {
        showToast('Connect the treadmill before continuing this record.');
        return;
    }
    sessionStartData.status = 'paused';
    sessionStartData.endReason = null;
    sessionStartData.endedAt = null;
    persistWalk();
    recoveryNotice.hidden = true;
});
newWalkRecordBtn.addEventListener('click', () => {
    if (sharedRecording()) {
        selectedTransport.resolveSession(bridgeSnapshot?.session?.sessionId, 'new').then(()=>refreshSharedHistory()).catch(historyError); return;
    }
    // Persist the boundary decision across reloads before dropping the old pointer.
    localStorage.setItem('treadmill_new_record_pending', '1');
    sessionActive = false;
    sessionStartData = null;
    clearCurrentSession();
    recoveryNotice.hidden = true;
    showToast('Previous record kept. New totals begin at the next running observation; earlier counters are excluded.');
});

function downloadJson(data, filename) {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    setTimeout(() => { document.body.removeChild(link); URL.revokeObjectURL(url); }, 100);
}
prepareNotionBtn.addEventListener('click', () => {
    preparedNotionExport = null;
    downloadNotionBtn.disabled = true;
    notionPreview.replaceChildren();
    try {
        preparedNotionExport = buildNotionExport(loadSessions());
        const summary = document.createElement('p');
        summary.textContent = `${preparedNotionExport.walks.length} finished/interrupted walks ready; ${preparedNotionExport.excluded.length} excluded. Download the file and provide it in this chat for review and import. This does not send data to Notion.`;
        notionPreview.appendChild(summary);
        for (const item of preparedNotionExport.walks) {
            const row = document.createElement('p');
            const m = item.metrics;
            row.textContent = `${item.properties.Activity} | ${item.status} | ${m.distanceMiles ?? 'unknown'} mi | ${m.durationSeconds ?? 'unknown'} seconds | ${m.steps ?? 'unknown'} steps | ${m.caloriesCal ?? 'unknown'} Cal | sample average ${m.averageSampleSpeedMph ?? 'unknown'} MPH | max ${m.maximumSpeedMph ?? 'unknown'} MPH | pace ${m.paceMinutesPerMile ?? 'unknown'} min/mi | cadence ${m.cadenceStepsPerMinute ?? 'unknown'} steps/min | ${item.properties['Data Quality']} | ${item.sourceId}`;
            notionPreview.appendChild(row);
        }
        for (const item of preparedNotionExport.excluded) {
            const row = document.createElement('p');
            row.textContent = `Excluded ${item.sourceId || 'record'}: ${item.reason}`;
            notionPreview.appendChild(row);
        }
        downloadNotionBtn.disabled = preparedNotionExport.walks.length === 0;
    } catch (err) {
        const error = document.createElement('p');
        error.textContent = 'Cannot prepare export: ' + err.message;
        notionPreview.appendChild(error);
    }
});
downloadNotionBtn.addEventListener('click', () => {
    if (preparedNotionExport?.walks.length) downloadJson(preparedNotionExport, 'pitpat-notion-walks.json');
});

// --- Import/Export History ---
if (exportHistoryBtn) {
    exportHistoryBtn.addEventListener('click', () => {
        let sessions;
        try { sessions = loadSessions(); } catch(error) { historyError(error); showToast(error.message); return; }
        const blob = new Blob([JSON.stringify(sessions, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'treadmill_sessions.json';
        document.body.appendChild(a);
        a.click();
        setTimeout(() => {
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }, 100);
        showToast('History exported.');
    });
}

if (importHistoryBtn && importHistoryInput) {
    importHistoryBtn.addEventListener('click', () => {
        importHistoryInput.value = '';
        importHistoryInput.click();
    });
    importHistoryInput.addEventListener('change', (e) => {
        const file = importHistoryInput.files && importHistoryInput.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = async function(event) {
            try {
                const imported = JSON.parse(event.target.result);
                if (Array.isArray(imported)) {
                    if (sessionActive) throw new Error('Resolve the current walk before importing history.');
                    if (imported.some(s => !s || typeof s !== 'object' || Array.isArray(s))) throw new Error('History must contain walk records.');
                    const incoming = PitPatWalks.identify(imported.map(americanSession));
                    if (sharedRecording()) {
                        await selectedTransport.importWalks(incoming);
                        await refreshSharedHistory();
                        if (sharedHistoryError) throw Error(sharedHistoryError);
                        showToast('History saved to the bridge.'); return;
                    }
                    const merged = loadLocalSessions();
                    for (const item of incoming) {
                        const existing = merged.find(s => s?.sessionId === item.sessionId);
                        if (!existing) merged.push(item);
                        else if (JSON.stringify(existing) !== JSON.stringify(item)) {
                            throw new Error('Conflicting walk ID. Existing history was not changed.');
                        }
                    }
                    saveSessions(merged);
                    renderSessionTable();
                    showToast('History imported successfully.');
                } else {
                    showToast('Invalid file format.');
                }
            } catch (err) {
                showToast('Failed to import: ' + err);
            }
        };
        reader.readAsText(file);
    });
}

function showToast(message, timeout = 4000) {
    if (snackbar) {
        snackbar.querySelector('.mdl-snackbar__text').textContent = message;
        snackbar.classList.add('mdl-snackbar--active');
        setTimeout(() => snackbar.classList.remove('mdl-snackbar--active'), timeout);
    } else {
        alert(message); // fallback
    }
}

// Capability discovery has no device or motion side effects.
if (typeof PitPatTransports !== 'undefined' && typeof fetch === 'function') {
    connectBtn.disabled = true;
    transportReady = PitPatTransports.select({fetch, bluetooth:navigator.bluetooth, WebSocket, location})
        .then(transport => {
            selectedTransport = transport;
            historyModePending = false;
            if (transport.kind === 'bridge') {
                bindBridgeTransport(transport);
                if (transport.observers) {
                    transport.observe().catch(error => safetyMessage(error.message));
                    const take = document.getElementById('takeControlBtn');
                    if (take) take.addEventListener('click',()=>transport.takeControl().catch(error=>safetyMessage(error.message)));
                }
            }
            if (sharedRecording()) refreshSharedHistory();
            else { initializeLocalRecovery(); renderSessionTable(); }
            const label = document.getElementById('transportStatus');
            if (label) label.textContent = transport.kind === 'bridge' ?
                (transport.simulator ? 'SIMULATOR — no physical treadmill' : 'Local Bluetooth bridge') : 'Direct Bluetooth (Chromium)';
            const ack = document.getElementById('acknowledgeRecoveryBtn');
            if (ack && transport.kind === 'bridge') ack.addEventListener('click', () => transport.acknowledgeRecovery(bridgeSnapshot?.fault_id).catch(error=>safetyMessage(error.message)));
            const recovery = document.getElementById('recoverBridgeBtn');
            if (recovery) {
                recovery.hidden = transport.kind !== 'bridge';
                recovery.addEventListener('click', () => connectBridge(true));
            }
            connectBtn.disabled = false;
        }).catch(error => {
            safetyMessage(error.message);
            const label = document.getElementById('transportStatus');
            if (label) label.textContent = 'Connection unavailable — reload after starting the local bridge';
        });
}
