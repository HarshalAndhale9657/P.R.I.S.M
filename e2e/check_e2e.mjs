import { chromium } from 'playwright';
import { fileURLToPath } from 'url';
import path from 'path';
import { mkdirSync, readFileSync } from 'fs';

const DIR = path.dirname(fileURLToPath(import.meta.url));
const FIX = path.join(DIR, 'fixtures');
const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:3000/';
const OUT = path.join(DIR, 'shots');
mkdirSync(OUT, { recursive: true });

const consoleErrors = [];
const pageErrors = [];

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text()); });
page.on('pageerror', e => pageErrors.push(e.message));

const log = (...a) => console.log(...a);
let ok = true;
const check = (c, m) => { log((c ? 'PASS' : 'FAIL') + ' - ' + m); ok = ok && c; };

try {
    await page.goto(BASE_URL, { waitUntil: 'networkidle' });
    log('[nav] loaded checker');

    await page.setInputFiles('#paper-input', path.join(FIX, 'paper.txt'));
    await page.setInputFiles('#refs-input', [path.join(FIX, 'ref.txt')]);
    log('[upload] paper + reference set');

    // paper + ref chips rendered
    const paperChips = await page.locator('#paper-chip .file-chip').count();
    const refChips = await page.locator('#refs-list .file-chip').count();
    check(paperChips === 1, 'paper chip rendered');
    check(refChips === 1, 'reference chip rendered');

    await page.waitForSelector('#btn-check:not([disabled])', { timeout: 5000 });
    await page.click('#btn-check');
    log('[check] clicked; waiting for results (model may load on first run)…');

    await page.waitForSelector('#view-results.active', { timeout: 90000 });
    await page.waitForSelector('.cs-num', { timeout: 10000 });
    await page.waitForTimeout(600);

    const overall = (await page.locator('.cs-num').innerText()).trim();
    const rows = await page.locator('.match-row').count();
    const marks = await page.locator('#doc-view mark.hl').count();
    log(`[results] overall=${overall}  match-rows=${rows}  highlights=${marks}`);
    check(rows >= 2, 'at least two matches listed (verbatim + paraphrase)');
    check(marks >= 2, 'document shows highlighted passages');

    await page.screenshot({ path: path.join(OUT, 'check-results.png'), fullPage: true });

    // W8 triage (ADR-0022): the prioritised panel, a type badge per match, and the coach card.
    const panel = await page.locator('.triage-panel .ti').count();
    const triBadges = await page.locator('.match-row .mtag-triage').count();
    check(panel >= 1, `"What to fix" panel lists prioritised action items (${panel})`);
    check(triBadges >= 1, `matches carry a triage type badge (${triBadges})`);

    // Click first highlight → comparison renders
    await page.locator('#doc-view mark.hl').first().click();
    await page.waitForTimeout(400);
    const cmp = await page.locator('#match-detail .cmp').count();
    check(cmp === 1, 'clicking a highlight shows the side-by-side comparison');
    const coach = await page.locator('#match-detail .coach').count();
    const fixText = coach ? (await page.locator('#match-detail .coach-fix').innerText()).trim() : '';
    check(coach === 1, 'the coach card shows the honest fix above the comparison');
    check(/honest fix/i.test(fixText) && fixText.length > 40, `coach card states a concrete fix ("${fixText.slice(0, 60)}…")`);
    await page.screenshot({ path: path.join(OUT, 'check-compare.png') });

    // Download the evidence report
    const [dl] = await Promise.all([
        page.waitForEvent('download'),
        page.click('#btn-download-report'),
    ]);
    const fname = dl.suggestedFilename();
    const html = readFileSync(await dl.path(), 'utf8');
    check(/^originality-report-.*\.html$/.test(fname), `report downloads with a sensible filename (${fname})`);
    check(html.includes('Originality Report') && html.includes('Matches') && html.includes('Method'),
          'downloaded report contains score, matches and limitations');
    check(html.includes('What to fix') && html.includes('Honest fix:'),
          'downloaded report carries the triage summary and per-match fixes');

    // New check resets to upload view
    await page.click('#btn-new-check');
    await page.waitForSelector('#view-upload.active', { timeout: 5000 });
    check(await page.locator('#paper-chip .file-chip').count() === 0, 'New check resets the form');

    log('\n===== RESULT =====');
    log('consoleErrors:', consoleErrors.length); consoleErrors.forEach(e => log('  ', e));
    log('pageErrors:', pageErrors.length); pageErrors.forEach(e => log('  ', e));
    check(pageErrors.length === 0, 'no uncaught page errors');
    log('\nPASS:', ok);
    process.exitCode = ok ? 0 : 1;
} catch (e) {
    log('[FATAL]', e.message);
    log('pageErrors:', pageErrors);
    await page.screenshot({ path: path.join(OUT, 'check-fatal.png'), fullPage: true }).catch(() => {});
    process.exitCode = 1;
} finally {
    await browser.close();
}
