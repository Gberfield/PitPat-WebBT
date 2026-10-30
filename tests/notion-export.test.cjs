const { test } = require('node:test');
const assert = require('node:assert/strict');
const { buildNotionExport, planNotionImport } = require('../walks.js');
const walk = overrides => ({ sessionId: 'walk-test', date: '2026-10-15T14:00:00-04:00',
    duration: 1800, distanceMiles: 1, steps: 2400, calories: '100 Cal', avgSpeed: 2,
    speedUnit: 'mph', status: 'completed', ...overrides });

test('all unfinished states are excluded from Notion preparation', () => {
    for (const status of ['running', 'paused', 'starting']) {
        const result = buildNotionExport([walk({ status })]);
        assert.equal(result.walks.length, 0); assert.equal(result.excluded.length, 1);
    }
});

test('legacy source telemetry can recover distance without estimating from speed', () => {
    const result = buildNotionExport([walk({ distanceMiles: undefined,
        sourceTelemetry: { distance: 1609.344, distance_unit: 'km' } })]);
    assert.equal(result.walks[0].properties['Distance Miles'], 1);
});

test('zero duration and distance do not produce Infinity, NaN or invented pace', () => {
    const result = buildNotionExport([walk({ duration: 0, distanceMiles: 0 })]);
    assert.equal(result.walks[0].metrics.paceMinutesPerMile, null);
    assert.equal(result.walks[0].metrics.cadenceStepsPerMinute, null);
    assert.equal(result.walks[0].metrics.averageSpeedMph, null);
    assert.equal(result.walks[0].properties['Calories kcal'], 100);
});

test('duplicate stable IDs block export rather than silently combining walks', () => {
    assert.throws(() => buildNotionExport([walk(), walk({ steps: 3000 })]), /Duplicate walk IDs/);
});

test('invalid IDs and dates are explicitly excluded', () => {
    for (const overrides of [{ sessionId: 'bad\nidentity' }, { date: 'invalid date' }]) {
        assert.equal(buildNotionExport([walk(overrides)]).walks.length, 0);
    }
});

test('unknown energy units are not interpreted as exercise Calories', () => {
    assert.equal(buildNotionExport([walk({ calories: '100 J' })]).walks[0].properties['Calories kcal'], undefined);
});

test('export derives Eastern date while retaining the source instant', () => {
    const result = buildNotionExport([walk({ date: '2026-10-16T01:00:00Z' })]).walks[0];
    assert.match(result.properties.Activity, /Oct 15, 2026/);
    assert.equal(result.properties['date:Activity Date:start'], '2026-10-16T01:00:00.000Z');
});

test('import planning requires a complete destination snapshot before proposing writes', () => {
    assert.equal(typeof planNotionImport, 'function');
    const bundle = buildNotionExport([walk()]);
    assert.throws(() => planNotionImport(bundle, { rows: [] }), /complete/);
});

test('repeat import produces no duplicate creates and changed metrics propose updates', () => {
    assert.equal(typeof planNotionImport, 'function');
    const bundle = buildNotionExport([walk()]);
    const snapshot = { destination: bundle.destination, complete: true, capturedAt: new Date().toISOString(), rows: [] };
    const first = planNotionImport(bundle, snapshot);
    assert.equal(first.creates.length, 1);
    snapshot.rows = [{ url: 'https://www.notion.so/example', properties: first.creates[0].properties,
        managedContent: first.creates[0].managedContent }];
    const second = planNotionImport(bundle, snapshot);
    assert.equal(second.creates.length, 0); assert.equal(second.updates.length, 0);
    assert.equal(second.unchanged.length, 1);
    const updated = planNotionImport(buildNotionExport([walk({ steps: 3000 })]), snapshot);
    assert.equal(updated.creates.length, 0); assert.equal(updated.updates.length, 1);
});

test('ambiguous Notion matches block import and destination properties cannot be injected', () => {
    assert.equal(typeof planNotionImport, 'function');
    const bundle = buildNotionExport([walk()]);
    const row = { url: 'https://www.notion.so/example', properties: bundle.walks[0].properties };
    assert.throws(() => planNotionImport(bundle, { destination: bundle.destination, complete: true, capturedAt: new Date().toISOString(), rows: [row, row] }), /multiple/);
    bundle.walks[0].properties.Type = 'Running';
    const plan = planNotionImport(bundle, { destination: bundle.destination, complete: true, capturedAt: new Date().toISOString(), rows: [] });
    assert.equal(plan.creates[0].properties.Type, 'Walking');
});

test('stale or missing snapshot timestamps block import planning', () => {
    const bundle = buildNotionExport([walk()]);
    for (const capturedAt of [undefined, '2000-01-01T00:00:00Z', 'invalid']) {
        assert.throws(() => planNotionImport(bundle, { destination: bundle.destination, complete: true, capturedAt, rows: [] }), /fresh/);
    }
});

test('known-to-unknown metric corrections require explicit review rather than stale updates', () => {
    const bundle = buildNotionExport([walk()]);
    const first = planNotionImport(bundle, { destination: bundle.destination, complete: true, capturedAt: new Date().toISOString(), rows: [] });
    const corrected = buildNotionExport([walk({ distanceMiles: undefined })]);
    const plan = planNotionImport(corrected, { destination: bundle.destination, complete: true, capturedAt: new Date().toISOString(),
        rows: [{ url: 'https://www.notion.so/example', properties: first.creates[0].properties, managedContent: first.creates[0].managedContent }] });
    assert.equal(plan.updates.length, 0); assert.equal(plan.creates.length, 0);
    assert.equal(plan.reviewRequired.length, 1);
    assert.deepEqual(plan.reviewRequired[0].unknownProperties, ['Distance Miles']);
});

test('delta-record exports preserve their counter baseline and label the duration basis', () => {
    const bundle = buildNotionExport([walk({ counterBaseline: { duration: 1800, distanceMiles: 1, steps: 2000, calories: 100 } })]);
    assert.match(bundle.walks[0].metrics.durationBasis, /delta/i);
    const plan = planNotionImport(bundle, { destination: bundle.destination, complete: true, capturedAt: new Date().toISOString(), rows: [] });
    assert.match(plan.creates[0].managedContent, /"counterBaseline"/);
});

test('confirmed source aliases prevent a split fragment from being imported as another walk', () => {
    const merged = buildNotionExport([walk({ reconciledSourceIds: ['pitpat:legacy-fragment'] })]);
    const empty = { destination: merged.destination, complete: true, capturedAt: new Date().toISOString(), rows: [] };
    const first = planNotionImport(merged, empty);
    const fragment = buildNotionExport([walk({ sessionId: 'legacy-fragment' })]);
    const again = planNotionImport(fragment, { ...empty, rows: [{ url: 'https://www.notion.so/example',
        properties: first.creates[0].properties, managedContent: first.creates[0].managedContent }] });
    assert.equal(again.creates.length, 0); assert.equal(again.updates.length, 0);
    assert.equal(again.reviewRequired.length, 1);
});

test('Notion date mapping uses minute precision while provenance retains exact source time', () => {
    const result = buildNotionExport([walk({ date: '2026-10-15T14:52:08.796Z' })]).walks[0];
    assert.equal(result.properties['date:Activity Date:start'], '2026-10-15T14:52:00.000Z');
    assert.equal(result.recordedStart, '2026-10-15T14:52:08.796Z');
});

test('Notion block spacing normalization does not trigger repeat updates', () => {
    const bundle = buildNotionExport([walk()]);
    const empty = { destination: bundle.destination, complete: true, capturedAt: new Date().toISOString(), rows: [] };
    const first = planNotionImport(bundle, empty).creates[0];
    const again = planNotionImport(bundle, { ...empty, rows: [{ url: 'https://www.notion.so/example',
        properties: first.properties, managedContent: first.managedContent.replace(/\n\n/g, '\n') }] });
    assert.equal(again.updates.length, 0); assert.equal(again.unchanged.length, 1);
});

test('shared/local identical IDs export once; conflicting evidence blocks export',()=>{
    const api=require('../walks.js');
    const row={schemaVersion:2,sessionId:'canonical-1',date:1700000000000,status:'completed',duration:60,steps:100,calories:'5 Cal',distanceMiles:.1,speedUnit:'mph',avgSpeed:2,opaque:{source:'kept'}};
    const combined=api.combineHistories([row],[JSON.parse(JSON.stringify(row))]);
    const result=api.buildNotionExport(combined);
    assert.equal(result.walks.length,1);assert.equal(result.walks[0].sourceId,'pitpat:canonical-1');
    assert.deepEqual(result.walks[0].rawSession.opaque,{source:'kept'});
    assert.throws(()=>api.combineHistories([row],[{...row,steps:101}]),/Conflicting/);
});

test('combined history normalizes known legacy fields before comparing IDs',()=>{
    const api=require('../walks.js');
    const old={sessionId:'legacy-known',date:1000,avgSpeed:1.609344,speedUnit:'kph',calories:'3 kcal'};
    const normalized={...old,schemaVersion:2,avgSpeed:1,speedUnit:'mph',calories:'3 Cal',originalMeasurements:{avgSpeed:1.609344,speedUnit:'kph',calories:'3 kcal'}};
    assert.equal(api.combineHistories([old],[normalized]).length,1);
});
