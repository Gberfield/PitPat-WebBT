// Pure export mapping shared by the dashboard and local validation tools.
// No network calls or Notion credentials live in the browser.
(function (root) {
    'use strict';
    const DESTINATION = 'collection://2027b6a8-5c8b-4be7-9110-87055d0d5aea';
    const number = value => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
    const instant = value => {
        if (value === null || value === undefined || value === '') return null;
        const date = new Date(value);
        return Number.isFinite(date.getTime()) ? date.toISOString() : null;
    };
    const eastern = value => new Intl.DateTimeFormat('en-US', {
        timeZone: 'America/New_York', year: 'numeric', month: 'short', day: 'numeric',
        hour: 'numeric', minute: '2-digit', timeZoneName: 'short',
    }).format(new Date(value));
    const id = () => root.crypto?.randomUUID?.() || `walk-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    function distanceMiles(walk) {
        const stored = number(walk.distanceMiles);
        if (stored !== null) return stored;
        const raw = walk.sourceTelemetry;
        if (!raw || number(raw.distance) === null) return null;
        if (raw.distance_unit === 'mi') return raw.distance / 1000;
        if (raw.distance_unit === 'km') return raw.distance / 1000 / 1.609344;
        return null;
    }

    function identify(sessions) {
        return sessions.map((session, index) => {
            if (!session || typeof session !== 'object' || Array.isArray(session) || session.sessionId) return session;
            // Persisted on migration, so inserting newer rows cannot change identity.
            const text = JSON.stringify(session);
            let hash = 2166136261;
            for (let i = 0; i < text.length; i++) hash = Math.imul(hash ^ text.charCodeAt(i), 16777619);
            return { ...session, sessionId: `legacy-${(hash >>> 0).toString(16)}-${index}` };
        });
    }

    function normalizeSession(session) {
        if (!session || typeof session !== 'object' || session.schemaVersion >= 2) return session;
        const result = {...session, schemaVersion:2,
            originalMeasurements:{avgSpeed:session.avgSpeed,speedUnit:session.speedUnit,calories:session.calories}};
        const value = Number(session.avgSpeed);
        if (session.avgSpeed !== null && session.avgSpeed !== '' && Number.isFinite(value)) {
            if (session.speedUnit === 'mph') result.avgSpeed = value;
            else if (['kph','km/h'].includes(session.speedUnit)) {result.avgSpeed=value/1.609344;result.speedUnit='mph';}
        }
        if (typeof session.calories === 'string') result.calories=session.calories.replace(/\s*kcal\s*$/i,' Cal');
        return result;
    }

    function combineHistories(local, shared) {
        const canonical = value => {
            if (Array.isArray(value)) return value.map(canonical);
            if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(k=>[k,canonical(value[k])]));
            return value;
        };
        const byId = new Map();
        for (const row of [...identify(local.map(normalizeSession)), ...identify(shared.map(normalizeSession))]) {
            if (!row || typeof row.sessionId !== 'string') throw Error('History contains a record without an identity');
            const existing = byId.get(row.sessionId);
            if (existing && JSON.stringify(canonical(existing)) !== JSON.stringify(canonical(row))) {
                throw Error('Conflicting walk ID: ' + row.sessionId + '. Resolve both records before exporting.');
            }
            byId.set(row.sessionId,row);
        }
        return [...byId.values()].sort((a,b)=>Number(b.date)-Number(a.date) || a.sessionId.localeCompare(b.sessionId));
    }

    function buildNotionExport(sessions) {
        const walks = [], excluded = [], ids = new Set();
        for (const walk of sessions) {
            if (!walk || typeof walk !== 'object' || typeof walk.sessionId !== 'string' || !/^[a-zA-Z0-9_-]{1,160}$/.test(walk.sessionId)) {
                excluded.push({ reason: 'Invalid record or missing stable ID' }); continue;
            }
            if (ids.has(walk.sessionId)) throw new Error('Duplicate walk IDs: resolve the history before exporting.');
            ids.add(walk.sessionId);
            if (walk.status && !['completed', 'interrupted', 'legacy'].includes(walk.status)) {
                excluded.push({ sourceId: walk.sessionId, reason: 'Walk is still active, paused or has an unknown state' }); continue;
            }
            const start = instant(walk.startedAt ?? walk.date);
            if (!start) { excluded.push({ sourceId: walk.sessionId, reason: 'Missing or invalid date' }); continue; }
            // This Notion connection stores dates at minute precision. Preserve
            // the exact instant separately in the managed source provenance.
            const notionDate = new Date(Math.floor(Date.parse(start) / 60000) * 60000).toISOString();
            const seconds = number(walk.duration);
            const miles = distanceMiles(walk);
            const steps = number(walk.steps);
            const energyMatch = typeof walk.calories === 'string' && walk.calories.match(/^\s*(\d+(?:\.\d+)?)\s*(?:Cal|kcal)\s*$/i);
            const calories = energyMatch ? number(Number(energyMatch[1])) : ['Cal', 'kcal'].includes(walk.caloriesUnit) ? number(walk.calories) : null;
            const mph = walk.speedUnit === 'mph' ? number(walk.avgSpeed) : null;
            const minutes = seconds === null ? null : seconds / 60;
            const metrics = {
                steps, durationSeconds: seconds, distanceMiles: miles, caloriesCal: calories,
                averageSampleSpeedMph: mph, maximumSpeedMph: number(walk.maxSpeedMph),
                averageSpeedMph: seconds > 0 && miles !== null ? miles * 3600 / seconds : null,
                paceMinutesPerMile: miles > 0 && minutes !== null ? minutes / miles : null,
                cadenceStepsPerMinute: minutes > 0 && steps !== null ? steps / minutes : null,
                activeDurationSeconds: number(walk.activeDurationSeconds),
                observedElapsedSeconds: number(walk.observedElapsedSeconds),
                durationBasis: walk.counterBaseline ? 'Device counter delta since new-record boundary; pause treatment is not verified' : 'Device cumulative duration; pause treatment is not verified',
                energyBasis: 'Device reported; active versus total energy is unknown',
            };
            const sourceId = `pitpat:${walk.sessionId}`;
            const sourceAliases = [...new Set(walk.reconciledSourceIds || [])].filter(alias => alias !== sourceId).sort();
            if (sourceAliases.some(alias => typeof alias !== 'string' || !/^pitpat:[a-zA-Z0-9_-]{1,160}$/.test(alias))) {
                throw new Error('Invalid reconciliation source identity.');
            }
            const properties = {
                Activity: `Treadmill walk — ${eastern(start)}`, Type: 'Walking', Source: 'Walking Pad',
                'date:Activity Date:start': notionDate, 'date:Activity Date:is_datetime': 1,
                'Data Quality': walk.coverage === 'complete' && walk.status === 'completed' &&
                    [seconds, miles, steps, calories].every(v => v !== null) ? 'Complete' : 'Partial',
                Context: `Source ID: ${sourceId}. Status: ${walk.status || 'legacy'}. ${walk.endReason || ''} Derived pace, cadence and distance/time speed use the device duration counter.`,
            };
            if (miles !== null) properties['Distance Miles'] = miles;
            if (minutes !== null) properties['Duration Minutes'] = minutes;
            if (calories !== null) properties['Calories kcal'] = calories;
            for (const alias of sourceAliases) properties.Context += ` Alias Source ID: ${alias}.`;
            walks.push({ sourceId, sourceAliases, properties, metrics, recordedStart: start,
                startBasis: walk.startBasis || 'First observation; actual start not recorded',
                recordedEnd: instant(walk.endedAt), status: walk.status || 'legacy',
                rawSession: walk });
        }
        return { format: 'pitpat-notion-walks', version: 1, destination: DESTINATION,
            displayTimeZone: 'America/New_York', walks, excluded,
            importPolicy: 'Preview, match exact Source ID in Context, create only missing walks, and verify readback. Update matching walks rather than creating duplicates. Never sum overlapping sources.' };
    }

    // This produces a reviewable plan only. Connected Notion tools perform writes.
    function planNotionImport(bundle, snapshot) {
        if (!snapshot || snapshot.complete !== true || snapshot.destination !== DESTINATION || !Array.isArray(snapshot.rows)) {
            throw new Error('A complete, fresh Exercise Log snapshot is required before planning writes.');
        }
        const age = Date.now() - new Date(snapshot.capturedAt).getTime();
        if (!Number.isFinite(age) || age < -30000 || age > 5 * 60 * 1000) {
            throw new Error('Snapshot is not fresh: fetch the complete destination again (maximum age five minutes).');
        }
        if (bundle?.format !== 'pitpat-notion-walks' || bundle.version !== 1 || bundle.destination !== DESTINATION || !Array.isArray(bundle.walks)) {
            throw new Error('Unsupported export format or destination.');
        }
        // Never execute supplied properties/content or trust a file's claimed destination.
        const validated = buildNotionExport(bundle.walks.map(item => item.rawSession));
        if (validated.walks.length !== bundle.walks.length) throw new Error('Export contains an ineligible walk.');
        const plan = { destination: DESTINATION, snapshotCapturedAt: snapshot.capturedAt,
            creates: [], updates: [], unchanged: [], reviewRequired: [] };
        for (const item of validated.walks) {
            const identities = [item.sourceId, ...item.sourceAliases];
            const matches = snapshot.rows.filter(row => {
                const matches = [...(row.properties?.Context || '').matchAll(/(?:^Source ID:|Alias Source ID:) (pitpat:[a-zA-Z0-9_-]+)\./g)];
                return matches.some(match => identities.includes(match[1]));
            });
            if (matches.length > 1) throw new Error(`Source ID ${item.sourceId} matches multiple Notion pages.`);
            const existing = matches[0];
            if (existing && (!existing.url || existing.properties.Source !== 'Walking Pad' || existing.properties.Type !== 'Walking')) {
                throw new Error('Matched row has a conflicting source/type or missing page URL. Review it first.');
            }
            const details = { sourceId: item.sourceId, ...item.metrics,
                sourceAliases: item.sourceAliases,
                reconciledSources: item.rawSession.reconciledSources || null,
                reconciliationNote: item.rawSession.reconciliationNote || null,
                start: item.recordedStart, end: item.recordedEnd, startBasis: item.startBasis,
                status: item.status, endReason: item.rawSession.endReason || null,
                counterBaseline: item.rawSession.counterBaseline || null,
                sourceTelemetry: item.rawSession.sourceTelemetry || null,
                speedSamples: item.rawSession.speedSamples || null,
                originalMeasurements: item.rawSession.originalMeasurements || null };
            const managedContent = '## PitPat walk details\nRecorded measurements and explicitly labeled derivations. Null means unknown.\n```json\n' + JSON.stringify(details, null, 2) + '\n```';
            const properties = { ...item.properties };
            // Keep any notes added to Context after a previous import.
            if (existing) properties.Context = existing.properties.Context;
            const payload = { sourceId: item.sourceId, properties, managedContent };
            if (!existing) { plan.creates.push(payload); continue; }
            const existingCanonical = existing.properties.Context.match(/^Source ID: (pitpat:[a-zA-Z0-9_-]+)\./)?.[1];
            const existingAliases = [...existing.properties.Context.matchAll(/Alias Source ID: (pitpat:[a-zA-Z0-9_-]+)\./g)].map(m => m[1]).sort();
            if (existingCanonical !== item.sourceId || JSON.stringify(existingAliases) !== JSON.stringify(item.sourceAliases)) {
                plan.reviewRequired.push({ ...payload, url: existing.url, before: existing,
                    reason: 'Source fragment or reconciliation changed; preserve the consolidated walk until reviewed.' });
                continue;
            }
            const unknownProperties = ['Distance Miles', 'Duration Minutes', 'Calories kcal']
                .filter(key => !(key in properties) && existing.properties[key] !== null && existing.properties[key] !== undefined);
            if (unknownProperties.length) {
                // A partial Notion update cannot silently leave stale known values.
                // Preserve evidence and require an explicit retain/clear disposition.
                plan.reviewRequired.push({ ...payload, url: existing.url, before: existing, unknownProperties });
                continue;
            }
            const same = Object.keys(properties).every(key => key === 'date:Activity Date:start' ?
                Date.parse(properties[key]) === Date.parse(existing.properties[key]) : properties[key] === existing.properties[key]);
            if (same && existing.managedContent === managedContent) plan.unchanged.push({ sourceId: item.sourceId, url: existing.url });
            else plan.updates.push({ ...payload, url: existing.url, before: existing });
        }
        return plan;
    }
    const api = { id, identify, normalizeSession, combineHistories, buildNotionExport, planNotionImport, eastern, distanceMiles };
    root.PitPatWalks = api;
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(globalThis);
