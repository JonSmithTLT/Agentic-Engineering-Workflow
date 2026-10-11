import { spawn } from 'node:child_process';
import fs from 'node:fs';
import { URL } from 'node:url';
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
const out = process.env.MAPS_OUTPUT ?? 'output/playwright-maps';
fs.mkdirSync(out, { recursive: true });
const ports = { worker: process.env.MAPS_WORKER_PORT ?? '4352', http: process.env.MAPS_HTTP_PORT ?? '4353' };
const owned = [], results = [];
const roots = ['a'.repeat(64), 'b'.repeat(64)];
function server(adapter) {
  const log = fs.openSync(`${out}/${adapter}-server.log`, 'w');
  const args = adapter === 'http' ? ['--experimental-strip-types', 'scripts/demo-server.mjs'] : ['node_modules/vite/bin/vite.js', 'preview', '--mode', 'demo', '--host', '127.0.0.1', '--port', ports.worker, '--strictPort', '--outDir', process.env.MAPS_STATIC_ROOT ?? 'dist-demo'];
  const child = spawn(process.execPath, args, { env: { ...process.env, DASHBOARD_PORT: ports.http, ...(process.env.MAPS_STATIC_ROOT ? { DASHBOARD_STATIC_ROOT: process.env.MAPS_STATIC_ROOT } : {}) }, stdio: ['ignore', log, log] });
  owned.push(child);
  return child;
}
async function ready(base, child) {
  for (let count = 0; count < 100; count++) {
    if (child.exitCode !== null) throw new Error('Owned Maps server exited');
    try { if ((await globalThis.fetch(base)).ok) return; } catch { /* owned startup */ }
    await new Promise(resolve => globalThis.setTimeout(resolve, 100));
  }
  throw new Error('Maps server startup timed out');
}
let browser;
async function trial(adapter, width) {
  const context = await browser.newContext({ viewport: { width, height: 900 }, serviceWorkers: adapter === 'http' ? 'block' : 'allow' });
  const page = await context.newPage(), reads = [], errors = [];
  const base = `http://127.0.0.1:${ports[adapter]}`;
  page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/api/v1/maps')) reads.push(request.url()); });
  page.on('pageerror', error => errors.push(error.message));
  await context.tracing.start({ screenshots: true, snapshots: true });
  try {
    await page.clock.install();
    await page.goto(`${base}/maps?fixture=F1`);
    await page.getByRole('heading', { name: `Map root ${roots[0]}` }).waitFor();
    await page.getByText('Rows omitted', { exact: true }).waitFor();
    assert.equal(new URL(page.url()).searchParams.get('map_root'), roots[0]);
    const detailReads = () => reads.filter(url => /\/structural\/[a-f0-9]{64}$/.test(new URL(url).pathname)).length;
    const summaries = () => reads.filter(url => new URL(url).pathname === '/api/v1/maps').length;
    const detailBefore = detailReads(), summaryBefore = summaries();
    await page.clock.fastForward(31000);
    await page.waitForFunction(() => !document.querySelector('button[disabled]'));
    assert(summaries() > summaryBefore, 'Displayed summary has 30-second cadence');
    assert.equal(detailReads(), detailBefore, 'Exact map details stay manual-only');
    await page.evaluate(() => window.dispatchEvent(new window.Event('focus')));
    await page.waitForTimeout(100);
    assert.equal(detailReads(), detailBefore, 'Foreground cannot refresh detail');
    await page.getByRole('tab', { name: 'Inputs', exact: true }).click();
    await page.getByText('<script>window.__mapsHostile=1</script>', { exact: true }).waitFor();
    assert.equal(await page.evaluate(() => window.__mapsHostile), undefined);
    assert.equal(await page.locator('.map-detail script').count(), 0);
    const beforeInputs = reads.length;
    await page.clock.fastForward(31000);
    assert.equal(reads.slice(beforeInputs).filter(url => new URL(url).pathname.endsWith('/inputs')).length, 0);
    await page.getByRole('button', { name: 'Next page', exact: true }).click();
    await page.getByText('src/fictional-060.ts', { exact: true }).waitFor();
    assert.equal(await page.getByText('<script>window.__mapsHostile=1</script>', { exact: true }).count(), 0);
    await page.getByRole('tab', { name: 'Provenance', exact: true }).click();
    await page.getByRole('heading', { name: 'Exact source and generator' }).waitFor();
    await page.getByRole('tab', { name: 'Provenance', exact: true }).focus();
    await page.keyboard.press('Home');
    assert.equal(await page.evaluate(() => document.activeElement?.id), 'map-detail-tab-sections');
    await page.getByText('Rows omitted', { exact: true }).waitFor();
    await page.getByRole('combobox', { name: /^Map section/ }).selectOption('test_candidates');
    await page.getByText('future_fixture_runner', { exact: true }).waitFor();
    assert.equal(await page.getByText('future_fixture_runner', { exact: true }).evaluate(node => node.closest('[role="status"]')?.textContent.includes('Unknown value:')), true);
    await page.getByRole('combobox', { name: /^Map section/ }).selectOption('limits_and_omissions');
    await page.getByText('Metadata unread', { exact: true }).waitFor();
    await page.screenshot({ path: `${out}/${adapter}-${width}-selected.png`, fullPage: true });
    await page.getByRole('tab', { name: 'Stored maps', exact: true }).click();
    await page.getByRole('button', { name: roots[0], exact: true }).waitFor();
    await page.getByRole('tab', { name: 'Stored maps', exact: true }).focus();
    await page.keyboard.press('Home');
    await page.getByText('Metadata unread', { exact: true }).waitFor();
    assert.equal(await page.evaluate(() => document.activeElement?.id), 'maps-tab-selected');
    await page.getByRole('tab', { name: 'Stored maps', exact: true }).click();
    await page.getByRole('button', { name: roots[0], exact: true }).waitFor();
    const summaryHidden = summaries();
    await page.clock.fastForward(31000);
    assert.equal(summaries(), summaryHidden, 'Concealed summary stops reads');
    await page.getByRole('row').filter({ has: page.getByRole('button', { name: roots[0], exact: true }) }).getByRole('button', { name: 'Use as A', exact: true }).click();
    await page.getByRole('button', { name: 'Next page', exact: true }).click();
    await page.getByText('Not on this loaded page;', { exact: false }).waitFor();
    await page.getByRole('row').filter({ has: page.getByRole('button', { name: roots[1], exact: true }) }).getByRole('button', { name: 'Use as B', exact: true }).click();
    assert.equal(await page.getByRole('table', { name: 'Stored maps · 50 entries per page' }).locator('tbody tr').count(), 1);
    await page.getByRole('tab', { name: 'Compare maps', exact: true }).click();
    await page.getByRole('heading', { name: 'Explicit comparison operands' }).waitFor();
    await page.getByRole('combobox', { name: /^Comparison section/ }).selectOption('directories');
    await page.getByText('Changes beyond the supplied cap remain unknown.', { exact: true }).waitFor();
    const diffs = reads.filter(url => new URL(url).pathname.endsWith('/diff')).length;
    await page.clock.fastForward(31000);
    await page.evaluate(() => window.dispatchEvent(new window.Event('focus')));
    await page.waitForTimeout(100);
    assert.equal(reads.filter(url => new URL(url).pathname.endsWith('/diff')).length, diffs);
    await page.evaluate(() => { document.documentElement.dataset.theme = 'dark'; document.documentElement.style.fontSize = '200%'; });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
    await page.screenshot({ path: `${out}/${adapter}-${width}-comparison-dark-text-scale.png`, fullPage: true });
    for (const invalid of ['map_root=HEAD', 'rev=old', 'revision=old', 'snapshot=old']) {
      const invalidReads = reads.length;
      await page.goto(`${base}/maps?fixture=F1&${invalid}`);
      await page.getByRole('alert').waitFor();
      await page.waitForTimeout(100);
      assert.equal(reads.length, invalidReads, 'Invalid/historical presentation causes no Maps read');
    }
    if (adapter === 'http') assert.equal(context.serviceWorkers().length, 0);
    assert.deepEqual(errors, []);
    results.push({ adapter, width, result: 'PASS', requests: reads.length, detail_reads_before_manual_navigation: detailBefore, scope: 'Compiled fixture adapters; virtual clock and CSS text scaling, not real browser zoom/live acceptance' });
    await context.tracing.stop();
    console.log(`PASS ${adapter} ${width} Maps bindings, manual reads, cadence, paging and explicit comparison`);
  } catch (error) {
    await page.screenshot({ path: `${out}/failure-${adapter}-${width}.png`, fullPage: true });
    await context.tracing.stop({ path: `${out}/failure-${adapter}-${width}.zip` });
    throw error;
  } finally { await context.close(); }
}
try {
  await Promise.all(Object.keys(ports).map(async adapter => { const child = server(adapter); await ready(`http://127.0.0.1:${ports[adapter]}`, child); }));
  browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? 'artifacts/playwright/browsers/chromium-1217/chrome-linux64/chrome', args: ['--no-sandbox'] });
  for (const adapter of ['http', 'worker']) for (const width of [1440, 390]) await trial(adapter, width);
  fs.writeFileSync(`${out}/result.json`, JSON.stringify({ browser: browser.version(), results }, null, 2) + '\n');
} finally { if (browser) await browser.close(); for (const child of owned) child.kill('SIGTERM'); }
