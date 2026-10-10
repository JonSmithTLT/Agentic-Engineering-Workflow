import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { URL } from 'node:url';
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
const out = process.env.HISTORY_SEARCH_OUTPUT ?? 'output/playwright-history-search';
fs.mkdirSync(out, { recursive: true });
const ports = { worker: process.env.HISTORY_SEARCH_WORKER_PORT ?? '4350', http: process.env.HISTORY_SEARCH_HTTP_PORT ?? '4351' };
const owned = [], checks = [], measurements = [];
function server(adapter) {
  const log = fs.openSync(`${out}/${adapter}-server.log`, 'w');
  const args = adapter === 'http' ? ['--experimental-strip-types', 'scripts/demo-server.mjs'] : ['node_modules/vite/bin/vite.js', 'preview', '--mode', 'demo', '--host', '127.0.0.1', '--port', ports.worker, '--strictPort'];
  const child = spawn(process.execPath, args, { env: { ...process.env, DASHBOARD_PORT: ports.http }, stdio: ['ignore', log, log] });
  owned.push(child);
  return child;
}
async function ready(base, child) {
  for (let i = 0; i < 100; i++) {
    if (child.exitCode !== null) throw new Error('Owned search server exited');
    try { if ((await globalThis.fetch(base)).ok) return; } catch { /* owned startup */ }
    await new Promise(resolve => globalThis.setTimeout(resolve, 100));
  }
  throw new Error('Search server startup timed out');
}
let browser;
async function check(adapter, layout, run) {
  const context = await browser.newContext({ viewport: layout === 'phone' ? { width: 390, height: 844 } : { width: 1440, height: 1000 }, serviceWorkers: adapter === 'http' ? 'block' : 'allow' });
  const page = await context.newPage(), reads = [], errors = [];
  const base = `http://127.0.0.1:${ports[adapter]}`;
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (new URL(request.url()).pathname === '/api/v1/history/search') reads.push({ url: request.url(), validator: request.headers()['if-none-match'] }); });
  await context.tracing.start({ screenshots: true, snapshots: true });
  try {
    await run(page, reads, base);
    assert.deepEqual(errors, []);
    if (adapter === 'http') assert.equal(context.serviceWorkers().length, 0);
    checks.push({ adapter, layout, result: 'PASS' });
    console.log(`PASS ${adapter} ${layout} explicit search and restoration`);
    await context.tracing.stop();
  } catch (error) {
    await page.screenshot({ path: `${out}/failure-${adapter}-${layout}.png`, fullPage: true });
    await context.tracing.stop({ path: `${out}/failure-${adapter}-${layout}.zip` });
    throw error;
  } finally { await context.close(); }
}
try {
  await Promise.all(Object.keys(ports).map(adapter => ready(`http://127.0.0.1:${ports[adapter]}`, server(adapter))));
  browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? path.resolve('artifacts/playwright/browsers/chromium-1217/chrome-linux64/chrome') });
  for (const adapter of ['http', 'worker']) for (const layout of ['desktop', 'phone']) await check(adapter, layout, async (page, reads, base) => {
    await page.goto(`${base}/history/search?fixture=F1`);
    const term = page.getByLabel('Term 1', { exact: true });
    await term.waitFor();
    assert.equal(await page.locator('nav[aria-label="Main navigation"] [aria-current="page"]').count(), 1);
    assert.equal(reads.length, 0);
    await page.getByRole('button', { name: 'Search', exact: true }).click();
    await page.getByText('Enter a literal term without control characters.', { exact: true }).waitFor();
    assert.equal(reads.length, 0);
    assert.equal(await term.evaluate(element => document.activeElement === element), true);
    await term.fill('fictional');
    await page.getByLabel('Since (UTC)', { exact: true }).fill('2026-10-02T11:59:59.000001Z');
    await page.getByLabel('Until (UTC)', { exact: true }).fill('2026-10-02T12:00:00.999Z');
    await term.evaluate(element => { element.dispatchEvent(new window.CompositionEvent('compositionstart', { bubbles: true })); element.form.requestSubmit(); });
    assert.equal(reads.length, 0);
    await term.evaluate(element => element.dispatchEvent(new window.CompositionEvent('compositionend', { bubbles: true })));
    await page.getByRole('button', { name: 'Search', exact: true }).click();
    await page.getByRole('heading', { name: 'Submitted search results', exact: true }).waitFor();
    assert.equal(reads.length, 1);
    assert.equal(await page.locator('.search-hit').count(), 2);
    assert((await page.locator('.search-results').innerText()).includes('Since UTC: 2026-10-02T12:00:00Z · Until UTC: 2026-10-02T12:00:00Z'));
    assert.equal(await page.locator('.search-snippet script, .search-snippet a').count(), 0);
    assert.equal(await page.evaluate(() => window.__searchHostile), undefined);
    assert(!page.url().includes('fictional'));
    await term.fill('unsubmitted draft');
    await page.evaluate(() => { window.dispatchEvent(new window.Event('focus')); document.dispatchEvent(new window.Event('visibilitychange')); });
    await page.waitForTimeout(250);
    assert.equal(reads.length, 1);
    await page.getByRole('link', { name: 'Archived removal reference', exact: true }).click();
    await page.getByText('AN-0001', { exact: true }).waitFor();
    await page.goBack();
    const origin = page.getByRole('link', { name: 'Archived removal reference', exact: true });
    await origin.waitFor();
    await page.waitForFunction(() => document.activeElement?.textContent === 'Archived removal reference');
    assert.equal(reads.length, 1);
    assert.equal(await term.inputValue(), 'unsubmitted draft');
    await page.getByLabel('Result limit', { exact: true }).click();
    await page.screenshot({ path: `${out}/${adapter}-${layout}-native-limit.png` });
    await page.keyboard.press('Escape');
    if (layout === 'phone') await page.getByRole('button', { name: 'Toggle navigation' }).click();
    await page.getByLabel('Appearance').selectOption('dark');
    if (layout === 'phone') await page.getByRole('link', { name: 'Raw history search', exact: true }).click();
    await page.screenshot({ path: `${out}/${adapter}-${layout}-results.png`, fullPage: true });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
    measurements.push({ adapter, layout, search_requests: reads.length, mounted_hits: await page.locator('.search-hit').count(), dom_nodes: await page.locator('*').count() });
    await page.getByRole('button', { name: 'Clear search', exact: true }).click();
    assert.equal(await term.inputValue(), '');
    assert.equal(await page.locator('.search-hit').count(), 0);
    assert.equal(reads.length, 1);
    await term.fill('fictional');
    await page.getByRole('button', { name: 'Search', exact: true }).click();
    await page.getByRole('heading', { name: 'Submitted search results', exact: true }).waitFor();
    assert.equal(reads.length, 2);
    assert.equal(reads[1].validator, undefined);
    await page.reload();
    await term.waitFor();
    assert.equal(await term.inputValue(), '');
    assert.equal(await page.locator('.search-hit').count(), 0);
    assert.equal(reads.length, 2);
    await page.goto(`${base}/history/search?fixture=F3`);
    await page.getByText('Raw history search is not offered on this project.', { exact: true }).waitFor();
    assert.equal(reads.length, 2);
  });
  for (const layout of ['desktop', 'phone']) await check('http', `${layout}-failure`, async (page, reads, base) => {
    await page.setViewportSize(layout === 'phone' ? { width: 390, height: 844 } : { width: 1440, height: 1000 });
    let mode = 'normal', release, started;
    await page.route('**/api/v1/history/search?**', async route => {
      if (mode === 'held') {
        const response = await route.fetch();
        started();
        await new Promise(resolve => { release = resolve; });
        await route.fulfill({ response }).catch(() => {});
      } else if (mode === 'normal') await route.continue();
      else await route.fulfill({ status: Number(mode), body: '', headers: { 'content-type': 'application/json' } });
    });
    await page.goto(`${base}/history/search?fixture=F1`);
    const term = page.getByLabel('Term 1', { exact: true });
    await term.fill('fictional');
    const search = page.getByRole('button', { name: 'Search', exact: true });
    await search.click();
    await page.locator('.search-hit').first().waitFor();
    const conditional = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/history/search');
    await search.click();
    assert.equal((await conditional).status(), 304);
    await page.getByRole('button', { name: 'Search', exact: true }).waitFor();
    assert.equal(reads.length, 2);
    assert(reads[1].validator);
    mode = '500';
    await search.click();
    await page.getByText('Last valid result retained; this search refresh failed.', { exact: true }).waitFor();
    assert.equal(await page.locator('.search-hit').count(), 2);
    mode = '403';
    await page.getByRole('button', { name: 'Retry submitted search' }).click();
    await page.waitForFunction(() => document.querySelectorAll('.search-hit').length === 0 && document.querySelector('[role="alert"]'));
    mode = 'normal';
    await page.getByRole('button', { name: 'Retry submitted search' }).click();
    await page.locator('.search-hit').first().waitFor();
    assert.equal(reads.at(-1).validator, undefined);
    mode = 'held';
    const held = new Promise(resolve => { started = resolve; });
    await search.click();
    await held;
    assert.equal(await page.getByRole('button', { name: 'Searching…', exact: true }).isDisabled(), true);
    await page.getByRole('button', { name: 'Clear search', exact: true }).click();
    release();
    await page.waitForTimeout(200);
    assert.equal(await page.locator('.search-hit').count(), 0);
    assert.equal(await term.inputValue(), '');
    assert.equal(await term.evaluate(element => document.activeElement === element), true);
    mode = 'normal';
    await term.fill('fictional');
    await search.click();
    await page.locator('.search-hit').first().waitFor();
    await page.evaluate(() => { document.documentElement.style.fontSize = '200%'; });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
    await page.screenshot({ path: `${out}/http-${layout}-text-200-percent.png`, fullPage: true });
    measurements.push({ adapter: 'http', layout, failure_checks: true, requests: reads.length, mounted_hits: await page.locator('.search-hit').count() });
  });
  fs.writeFileSync(`${out}/result.json`, JSON.stringify({ checks, measurements, browser: browser.version(), scope: 'Compiled fixture adapters, not live Engine acceptance; text scaling is not real browser zoom' }, null, 2) + '\n');
} finally { if (browser) await browser.close(); for (const child of owned) child.kill('SIGTERM'); }
