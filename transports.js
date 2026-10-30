(function(root, factory) {
    const api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    else root.PitPatTransports = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
    class BridgeTransport {
        constructor(bootstrap, env) {
            this.kind = 'bridge'; this.simulator = bootstrap.simulator;
            this.observers = bootstrap.observers === true; this.recording = bootstrap.recording; this.snapshot = null;
            this.token = bootstrap.token; this.env = env;
            this.generation = 0; this.sequence = 0; this.serial = 0;
            this.pending = new Map(); this.listeners = new Set(); this.claimed = false;
        }
        onEvent(callback) { this.listeners.add(callback); return () => this.listeners.delete(callback); }
        emit(event) { for (const callback of this.listeners) { try { callback(event); } catch (err) { console.error(err); } } }
        open() {
            if (this.opening) return this.opening;
            if (this.authorized && this.socket?.readyState === 1) return Promise.resolve();
            const socket = new this.env.WebSocket(this.env.location.origin.replace(/^http/, 'ws') + '/api/ws');
            this.socket = socket; this.sequence = 0; this.authorized = false;
            let rejectOpen;
            const promise = new Promise((resolve, reject) => {
                rejectOpen = reject;
                const timer = setTimeout(() => { reject(Error('Local bridge authorization timed out')); socket.close(); }, 4000);
                socket.onopen = () => socket.send(JSON.stringify({v:1, op:'authorize', token:this.token}));
                socket.onmessage = message => {
                    if (this.socket !== socket) return;
                    let data;
                    try { data = JSON.parse(message.data); } catch { socket.close(); return; }
                    if (data.v !== 1) { socket.close(); return; }
                    if (data.event === 'authorized' && !this.authorized) {
                        this.authorized = true; this.generation = data.generation; clearTimeout(timer);
                        this.acceptSnapshot(data.snapshot);
                        this.lease = setInterval(() => {
                            const generation=this.generation;
                            if (this.claimed || this.snapshot?.is_recovery_claimant) this.command('renew').catch(() => { if (this.claimed && generation === this.generation) socket.close(); });
                        }, 1000);
                        resolve(); return;
                    }
                    if (!this.authorized) { socket.close(); return; }
                    if (data.id) {
                        const pending = this.pending.get(data.id);
                        if (!pending) return;
                        this.pending.delete(data.id); clearTimeout(pending.timer);
                        if (data.generation < this.generation || data.generation < pending.generation ||
                            (data.generation !== pending.generation && !['connect','stop_disconnect','release','take_control','observe','acknowledge_recovery'].includes(pending.op))) {
                            pending.reject(Error('Obsolete bridge response')); return;
                        }
                        if (data.ok) { this.generation = Math.max(this.generation, data.generation);
                            if (['observe','take_control','resolve_session','acknowledge_recovery'].includes(pending.op)) this.acceptSnapshot(data.result);
                            pending.resolve(data.result); }
                        else pending.reject(Error(data.error || 'Bridge request failed'));
                        return;
                    }
                    if ((!this.observers && !this.claimed) || !Number.isInteger(data.generation) || data.generation < this.generation ||
                        !Number.isInteger(data.seq) || data.seq <= this.sequence) return;
                    this.generation = data.generation; this.sequence = data.seq;
                    this.acceptSnapshot(data.snapshot);
                    if (data.event === 'disconnected' || data.event === 'lost') this.claimed = false;
                    this.emit(data);
                };
                socket.onerror = () => { reject(Error('Local bridge unavailable')); socket.close(); };
                socket.onclose = () => {
                    clearTimeout(timer);
                    if (this.socket !== socket) return;
                    clearInterval(this.lease); this.authorized = false; this.claimed = false;
                    const error = Error('Local bridge connection lost; belt state is unconfirmed');
                    rejectOpen(error);
                    for (const pending of this.pending.values()) { clearTimeout(pending.timer); pending.reject(error); }
                    this.pending.clear(); this.emit({event:'lost', data:{message:error.message}});
                };
            });
            this.opening = promise;
            promise.then(() => { if (this.opening === promise) this.opening = null; }, () => { if (this.opening === promise) this.opening = null; });
            return promise;
        }
        acceptSnapshot(snapshot) {
            if (!this.observers || !snapshot) return;
            this.snapshot = snapshot;
            this.claimed = snapshot.is_owner === true;
            this.emit({event:'snapshot', snapshot, data:snapshot});
        }
        async historyRequest(path, options = {}) {
            const response = await this.env.fetch.call(globalThis, path, {
                cache:'no-store', ...options,
                headers:{'X-PitPat-Token':this.token, ...(options.headers || {})}
            });
            if (!response.ok) throw Error('Shared history request failed (HTTP ' + response.status + ')');
            return response.json();
        }
        observe() { return this.command('observe'); }
        takeControl() { return this.command('take_control'); }
        async acknowledgeRecovery(faultId) {
            await this.stop();
            if (this.snapshot?.fault_id !== faultId) throw Error('Fault changed; review current state');
            return this.command('acknowledge_recovery', {fault_id:faultId,stop_confirmation_id:this.snapshot?.stop_confirmation_id});
        }
        walks({limit=100,before} = {}) {
            return this.historyRequest('/api/walks?limit=' + limit + (before ? '&before=' + encodeURIComponent(before) : ''));
        }
        importWalks(records) {
            return this.historyRequest('/api/walks/import', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({walks:records})});
        }
        resolveSession(sessionId, choice) { return this.command('resolve_session',{session_id:sessionId,choice}); }
        async command(op, args = {}) {
            await this.open();
            const id = String(++this.serial), generation = this.generation;
            return new Promise((resolve, reject) => {
                const timer = setTimeout(() => {
                    this.pending.delete(id); reject(Error('Bridge request timed out; state is unconfirmed'));
                    this.socket?.close(); // Expire ownership and let the backend request Stop.
                }, op === 'connect' ? 26000 : 8000);
                this.pending.set(id, {resolve, reject, timer, generation, op});
                try { this.socket.send(JSON.stringify({v:1,id,op,generation,args})); }
                catch (error) { clearTimeout(timer); this.pending.delete(id); reject(error); this.socket.close(); }
            });
        }
        discover() { return this.command('discover').then(result => result.devices); }
        async connect(deviceId, recover = false) {
            await this.open(); if (!this.observers) this.claimed = true;
            try { return await this.command('connect', recover ? {recover:true} : {device_id:deviceId}); }
            catch (error) { this.claimed = false; throw error; }
        }
        stop() { return this.command('stop'); }
        stopDisconnect() { return this.command('stop_disconnect'); }
    }
    async function select(env) {
        // Firefox requires the Window receiver for its native fetch function.
        const response = await env.fetch.call(globalThis, '/api/bootstrap', {cache:'no-store'});
        if (response.status === 404) {
            if (typeof env.bluetooth?.requestDevice === 'function') return {kind:'direct'};
            throw Error('This browser needs the local PitPat bridge. Start it and open its dashboard URL.');
        }
        if (response.status !== 200) throw Error('Local bridge is unavailable (HTTP ' + response.status + ')');
        const info = await response.json();
        if (info.v !== 1 || info.transport !== 'bridge' || typeof info.token !== 'string' ||
            typeof info.simulator !== 'boolean' || info.lease_ms !== 6000) throw Error('Invalid bridge bootstrap');
        return new BridgeTransport(info, env);
    }
    return {select, BridgeTransport};
});
