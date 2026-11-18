#!/usr/bin/env bun
// delend-health-race: Emergent experimental health checker
// Races multiple health probes to detect flail states.
// Uses delend-iterate logic for async/await-aware feedback.

import { spawn } from 'child_process';
import { resolve } from 'path';

const BIN_DIR = resolve(__dirname);
const HEALTH_CHECKS = [
    { name: 'kite-keepalive', cmd: 'git', args: ['rev-parse', '--verify', 'HEAD'] },
    { name: 'hatch-gate', cmd: 'bash', args: [resolve(BIN_DIR, 'hatch-gate'), 'HEAD'] },
    { name: 'market-loop', cmd: 'test', args: ['-f', resolve(BIN_DIR, '../agents/weaver/bin/market-loop.ts')] },
];

async function runCheck(check: any): Promise<{ name: string; status: 'ok' | 'fail' | 'timeout'; error?: string }> {
    return new Promise((resolve) => {
        const start = Date.now();
        const proc = spawn(check.cmd, check.args, { stdio: 'ignore' });
        
        proc.on('exit', (code) => {
            const duration = Date.now() - start;
            if (code === 0) {
                resolve({ name: check.name, status: 'ok', error: undefined });
            } else {
                resolve({ name: check.name, status: 'fail', error: `Exit code ${code}` });
            }
        });

        // Timeout after 5 seconds
        setTimeout(() => {
            proc.kill();
            resolve({ name: check.name, status: 'timeout', error: 'Timeout' });
        }, 5000);
    });
}

async function main() {
    console.log('[DELEND-HEALTH-RACE] Starting emergent health race...');
    
    const results = await Promise.all(HEALTH_CHECKS.map(runCheck));
    
    let flailDetected = false;
    for (const result of results) {
        const status = result.status === 'ok' ? 'OK' : 'FAIL';
        console.log(`[DELEND-HEALTH-RACE] ${result.name}: ${status} ${result.error ? `(${result.error})` : ''}`);
        if (result.status !== 'ok') {
            flailDetected = true;
        }
    }

    if (flailDetected) {
        console.log('[DELEND-HEALTH-RACE] FLAIL DETECTED. Initiating self-heal via delend-oracle apply...');
        // In a real scenario, this would trigger delend-oracle apply
    } else {
        console.log('[DELEND-HEALTH-RACE] All systems nominal.');
    }
}

main().catch(console.error);
