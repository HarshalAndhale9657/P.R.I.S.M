import { chromium } from 'playwright';
import { fileURLToPath } from 'url';
import path from 'path';
import { mkdirSync } from 'fs';

const DIR = path.dirname(fileURLToPath(import.meta.url));
const FIX = path.join(DIR, 'fixtures');
const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:3000/';
const OUT = path.join(DIR, 'shots');
mkdirSync(OUT, { recursive: true });

const consoleErrors = [], pageErrors = [];
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text()); });
page.on('pageerror', e => pageErrors.push(e.message));

const log = (...a) => console.log(...a);
let ok = true;
const check = (c, m) => { log((c ? 'PASS' : 'FAIL') + ' - ' + m); ok = ok && c; };

try {
    await page.goto(BASE_URL, { waitUntil: 'networkidle' });
    await page.setInputFiles('#paper-input', path.join(FIX, 'academic_paper.txt'));

    // Toggle academic search ON — the button must enable with NO reference files.
    // (Visually-hidden custom switch; a real user clicks the label. Drive it via the change event.)
    await page.evaluate(() => {
        const cb = document.getElementById('academic-toggle');
        cb.checked = true;
        cb.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await page.waitForSelector('#btn-check:not([disabled])', { timeout: 5000 });
    check(true, 'academic toggle enables Check with no reference files');

    await page.click('#btn-check');
    log('[check] academic search running (network + model)…');
    await page.waitForSelector('#view-results.active', { timeout: 120000 });
    await page.waitForSelector('.cs-num', { timeout: 10000 });
    await page.waitForTimeout(700);

    const overall = (await page.locator('.cs-num').innerText()).trim();
    const rows = await page.locator('.match-row').count();
    const originTags = await page.locator('.match-row .origin-tag').count();
    log(`[results] overall=${overall}  matches=${rows}  openalex-tags=${originTags}`);
    check(rows >= 1, 'at least one academic match found');
    check(originTags >= 1, 'match is tagged with its OpenAlex origin');

    // Open the comparison and confirm the source links out.
    await page.locator('.match-row').first().click();
    await page.waitForTimeout(400);
    const link = await page.locator('#match-detail a.cmp-src').count();
    check(link >= 1, 'source in comparison links to the OpenAlex record');

    await page.screenshot({ path: path.join(OUT, 'check-academic.png'), fullPage: true });

    log('\n===== RESULT =====');
    log('consoleErrors:', consoleErrors.length); consoleErrors.forEach(e => log('  ', e));
    log('pageErrors:', pageErrors.length); pageErrors.forEach(e => log('  ', e));
    check(pageErrors.length === 0, 'no uncaught page errors');
    log('\nPASS:', ok);
    process.exitCode = ok ? 0 : 1;
} catch (e) {
    log('[FATAL]', e.message);
    await page.screenshot({ path: path.join(OUT, 'check-academic-fatal.png'), fullPage: true }).catch(() => {});
    process.exitCode = 1;
} finally {
    await browser.close();
}
