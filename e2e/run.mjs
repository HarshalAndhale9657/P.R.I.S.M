/**
 * P.R.I.S.M. browser E2E runner.
 *
 *   node run.mjs                 # offline specs (references + translated)
 *   E2E_NETWORK=1 node run.mjs   # also the academic-search spec (talks to OpenAlex/arXiv)
 *
 * Expects the backend on :8000 and the frontend on :3000 (override with E2E_BASE_URL).
 * Each spec is a standalone script; this just runs them in sequence and fails if any fail.
 */
import { spawnSync } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';

const DIR = path.dirname(fileURLToPath(import.meta.url));
const specs = ['check_e2e.mjs', 'check_translated_e2e.mjs'];
if (process.env.E2E_NETWORK === '1') specs.push('check_academic_e2e.mjs');

let failed = 0;
for (const spec of specs) {
    console.log(`\n━━━━━━━━━━ ${spec} ━━━━━━━━━━`);
    const r = spawnSync(process.execPath, [path.join(DIR, spec)], { stdio: 'inherit', env: process.env });
    if (r.status !== 0) failed++;
}
console.log(`\n${specs.length - failed}/${specs.length} specs passed`);
process.exit(failed ? 1 : 0);
