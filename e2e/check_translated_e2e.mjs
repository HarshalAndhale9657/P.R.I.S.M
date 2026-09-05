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
    await page.setInputFiles('#paper-input', path.join(FIX, 'translated_paper.txt'));
    await page.setInputFiles('#refs-input', [path.join(FIX, 'fr_ref.txt')]);
    await page.waitForSelector('#btn-check:not([disabled])', { timeout: 5000 });
    await page.click('#btn-check');
    log('[check] cross-lingual check running…');

    await page.waitForSelector('#view-results.active', { timeout: 90000 });
    await page.waitForSelector('.cs-num', { timeout: 10000 });
    await page.waitForTimeout(600);

    const translatedBadges = await page.locator('.match-row .mtag-translated').count();
    const langPairs = await page.locator('.match-row .lang-pair').count();
    const translatedBar = await page.locator('.cs-bar-fill.hl-translated').count();
    log(`[results] translated-badges=${translatedBadges}  lang-pairs=${langPairs}  translated-bar=${translatedBar}`);
    check(translatedBadges >= 1, 'a cross-lingual copy is labelled "Translated"');
    check(langPairs >= 1, 'the language pair (e.g. FR→EN) is shown');

    // Highlight uses the translated colour class
    const trMarks = await page.locator('#doc-view mark.hl-translated').count();
    check(trMarks >= 1, 'the translated passage is highlighted in the document');

    await page.screenshot({ path: path.join(OUT, 'check-translated.png'), fullPage: true });

    log('\n===== RESULT =====');
    log('consoleErrors:', consoleErrors.length); consoleErrors.forEach(e => log('  ', e));
    log('pageErrors:', pageErrors.length); pageErrors.forEach(e => log('  ', e));
    check(pageErrors.length === 0, 'no uncaught page errors');
    log('\nPASS:', ok);
    process.exitCode = ok ? 0 : 1;
} catch (e) {
    log('[FATAL]', e.message);
    await page.screenshot({ path: path.join(OUT, 'check-translated-fatal.png'), fullPage: true }).catch(() => {});
    process.exitCode = 1;
} finally {
    await browser.close();
}
