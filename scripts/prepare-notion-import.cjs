#!/usr/bin/env node
// Reads local files and prints a plan. This script never connects to Notion.
const fs = require('node:fs');
const { planNotionImport } = require('../walks.js');
try {
    const [bundlePath, snapshotPath] = process.argv.slice(2);
    if (!bundlePath || !snapshotPath) throw new Error('Usage: node scripts/prepare-notion-import.cjs EXPORT.json SNAPSHOT.json');
    const bundle = JSON.parse(fs.readFileSync(bundlePath, 'utf8'));
    const snapshot = JSON.parse(fs.readFileSync(snapshotPath, 'utf8'));
    process.stdout.write(JSON.stringify(planNotionImport(bundle, snapshot), null, 2) + '\n');
} catch (err) {
    process.stderr.write('Import planning stopped: ' + err.message + '\n');
    process.exitCode = 1;
}
