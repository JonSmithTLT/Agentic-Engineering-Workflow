import { spawn } from 'node:child_process';
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { URL } from 'node:url';
const out = process.env.W04_BROWSER_OUTPUT ?? 'output/playwright-w04';
const httpPort = process.env.W04_HTTP_PORT ?? '4260', workerPort = process.env.W04_WORKER_PORT ?? '4261';
fs.mkdirSync(out, { recursive: true });
const children = [], checks = [], measurements = [];
let browser;
function server(port, args) { const log = fs.openSync(`${out}/server-${port}.log`, 'w'); const child = spawn(process.execPath, args, { env: { ...process.env, DASHBOARD_PORT: port }, stdio: ['ignore', log, log] }); children.push(child); return child; }
const http = server(httpPort, ['--experimental-strip-types', 'scripts/demo-server.mjs']);
const worker = server(workerPort, ['node_modules/vite/bin/vite.js', 'preview', '--mode', 'demo', '--host', '127.0.0.1', '--port', workerPort, '--strictPort']);
async function ready(port, child) { for (let i = 0; i < 100; i++) { if (child.exitCode !== null) throw new Error('Owned server exited'); try { if ((await globalThis.fetch(`http://127.0.0.1:${port}`)).ok) return; } catch { /* Startup */ } await new Promise(r => globalThis.setTimeout(r, 100)); } throw new Error('Server startup failed'); }
async function check(name, mode, run, options = {}) {
  const base = `http://127.0.0.1:${mode === 'http' ? httpPort : workerPort}`;
  const context = await browser.newContext({ viewport: options.phone ? { width: 390, height: 844 } : { width: 1440, height: 1000 }, serviceWorkers: mode === 'http' ? 'block' : 'allow', permissions: ['clipboard-read', 'clipboard-write'], colorScheme: options.dark ? 'dark' : 'light' });
  const page = await context.newPage(), errors = [], failures = [], requests = [];
  const expected = options.expected ?? [];
  const allowed = (url, status) => expected.some(e => { const u = new URL(url); return u.pathname === e.path && u.searchParams.get('case') === e.case && (status === undefined || e.status === status); });
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error' && !(/Failed to load resource/.test(m.text()) && allowed(m.location().url))) errors.push(m.text()); });
  page.on('response', r => { if (r.status() >= 400 && !allowed(r.url(), r.status())) failures.push({ url: r.url(), status: r.status() }); });
  page.on('request', r => requests.push({ url: r.url(), method: r.method(), etag: r.headers()['if-none-match'] }));
  await context.tracing.start({ screenshots: true, snapshots: true });
  const started = Date.now();
  try {
    await run(page, base, requests);
    assert.deepEqual(errors, [], 'No unexpected console/page errors'); assert.deepEqual(failures, [], 'No unexpected failed responses');
    assert(requests.every(r => ['GET', 'HEAD'].includes(r.method)));
    if (mode === 'http') { assert.equal(context.serviceWorkers().length, 0); assert(!requests.some(r => /mockServiceWorker|assets\/browser-/.test(r.url))); }
    checks.push({ name, mode, result: 'PASS', duration_ms: Date.now() - started }); console.log('PASS ' + mode + ' ' + name);
    await context.tracing.stop();
  } catch (error) { await page.screenshot({ path: `${out}/failure-${checks.length}.png`, fullPage: true }); await context.tracing.stop({ path: `${out}/failure-${checks.length}.zip` }); throw error; }
  finally { await context.close(); }
}
const sourceA = page => page.getByRole('region', { name: 'Source A', exact: true });
const sourceB = page => page.getByRole('region', { name: 'Source B', exact: true });
async function choose(page, side, source) { await page.getByRole('button', { name: `Change ${side}` }).click(); await page.getByRole('button', { name: `Select ${source} for ${side}`, exact: true }).click(); await (side === 'A' ? sourceA(page) : sourceB(page)).getByText(source, { exact: true }).waitFor(); }
const storyLink = '/compare?fixture=F1&a_source=SRC-Removal&b_source=SRC-Retry';
try {
  await Promise.all([ready(httpPort, http), ready(workerPort, worker)]);
  browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? path.resolve('artifacts/playwright/browsers/chromium-1217/chrome-linux64/chrome') });
  for (const mode of ['http', 'worker']) for (const phone of [false, true]) await check(`${phone ? 'phone' : 'desktop'} failed removal/retry and later inclusion`, mode, async (page, base, requests) => {
    await page.goto(base + '/compare?fixture=F1');
    await choose(page, 'A', 'SRC-Removal'); await choose(page, 'B', 'SRC-Retry');
    await page.getByText('Removal broke generated protocol callers; the change was reverted.', { exact: true }).waitFor();
    await page.getByText(/After refreshing compile_commands, generated callers were identified/).waitFor();
    await page.getByLabel('Harness run A').selectOption('CLANGD-R-A2-2'); await page.getByLabel('Harness run B').selectOption('CLANGD-R-A2-4');
    await page.getByRole('tab', { name: 'Configuration', exact: true }).click(); await page.getByText('stale-db-fictional', { exact: true }).waitFor(); await page.getByText('refreshed-db-fictional', { exact: true }).waitFor();
    await page.evaluate(() => window.scrollTo(0, 0)); await page.screenshot({ path: `${out}/${mode}-${phone ? 'phone' : 'desktop'}-comparison.png`, fullPage: true });
    await page.getByRole('tab', { name: 'References', exact: true }).click();
    await page.getByRole('button', { name: 'Inspect PKT-Removal', exact: true }).click();
    await page.getByRole('heading', { name: 'Context packet PKT-Removal' }).waitFor(); await page.getByText('Mistaken hypothesis: missing index references suggest dead code.', { exact: true }).waitFor();
    await page.getByRole('tab', { name: 'Receipts', exact: true }).click(); await page.getByText('No delivery receipt supplied.', { exact: true }).waitFor();
    await page.getByRole('button', { name: 'Back to comparison', exact: true }).click();
    await page.waitForFunction(() => document.activeElement?.textContent === 'Inspect PKT-Removal');
    await page.getByRole('button', { name: 'Inspect PKT-Retry', exact: true }).click();
    await page.getByText('Refreshed compile_commands reveals generated callers.', { exact: true }).waitFor();
    assert.equal(await page.getByText('J-05', { exact: true }).count(), 0);
    await page.evaluate(() => window.scrollTo(0, 0)); await page.screenshot({ path: `${out}/${mode}-${phone ? 'phone' : 'desktop'}-packet.png`, fullPage: true });
    await page.getByRole('tab', { name: 'Selection & budget', exact: true }).click(); await page.getByText('fictional-estimator-v1', { exact: true }).waitFor();
    await page.getByRole('tab', { name: 'Receipts', exact: true }).click(); await page.getByText('RECEIPT-Retry-DELIVERY', { exact: true }).waitFor(); await page.getByText('RECEIPT-Retry-CITATION', { exact: true }).waitFor(); await page.getByText('No benefit evaluation supplied.', { exact: true }).waitFor();
    await page.getByRole('tab', { name: 'Provenance', exact: true }).click(); await page.getByText('CLANGD-D42', { exact: true }).waitFor();
    await page.reload(); await page.getByText('CLANGD-D42', { exact: true }).waitFor();
    await page.getByRole('button', { name: 'Copy dashboard link', exact: true }).click(); const copied = await page.evaluate(() => navigator.clipboard.readText()); assert.equal(new URL(copied).searchParams.get('packet_tab'), 'provenance');
    await page.getByRole('button', { name: 'Back to comparison', exact: true }).click(); await choose(page, 'B', 'SRC-Later');
    await page.getByRole('tab', { name: 'References', exact: true }).click(); await page.getByRole('button', { name: 'Inspect PKT-Later', exact: true }).click(); await page.getByRole('link', { name: 'J-05', exact: true }).click(); await page.getByRole('heading', { name: /^J-05 · Refresh/ }).waitFor(); await page.goBack(); await page.getByRole('link', { name: 'J-05', exact: true }).waitFor();
    await page.getByRole('tab', { name: 'Receipts', exact: true }).click(); await page.getByText('RECEIPT-Later-DELIVERY', { exact: true }).waitFor(); await page.getByText('No output citation receipt supplied.', { exact: true }).waitFor(); await page.getByText('No benefit evaluation supplied.', { exact: true }).waitFor();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth), false);
    measurements.push({ mode, viewport: phone ? 'phone' : 'desktop', requests: requests.filter(r => r.url.includes('/api/preview/investigation/')).length, dom_nodes: await page.locator('*').count() });
  }, { phone });
  await check('paging, scope-bound copy/reload, filters, independent selection and swap', 'http', async (page, base) => {
    await page.goto(base + '/compare?fixture=F1&investigation_case=large&choose=a');
    await page.getByRole('button', { name: 'Select L-0000 for A', exact: true }).waitFor(); assert.equal(await page.locator('.source-chooser tbody tr').count(), 50);
    await page.getByRole('button', { name: 'Next page', exact: true }).click(); await page.getByRole('button', { name: 'Select L-0050 for A', exact: true }).waitFor(); await page.reload(); await page.getByRole('button', { name: 'Select L-0050 for A', exact: true }).waitFor();
    await page.getByRole('button', { name: 'First page', exact: true }).click(); await page.getByRole('button', { name: 'Select L-0000 for A', exact: true }).click();
    const paired = new URL(page.url()); paired.searchParams.set('b_source', 'SRC-Retry'); await page.goto(paired.href); await sourceB(page).getByText('SRC-Retry', { exact: true }).waitFor();
    await page.getByRole('tab', { name: 'References', exact: true }).click(); await page.getByRole('button', { name: 'Inspect PKT-Retry', exact: true }).click(); await page.locator('.packet-items > li').first().waitFor(); assert.equal(await page.locator('.packet-items > li').count(), 50); await page.getByRole('button', { name: 'Next page', exact: true }).click(); await page.waitForURL(/packet_cursor=/); await page.reload(); await page.locator('.packet-items > li').first().waitFor(); assert.equal(await page.locator('.packet-items > li').count(), 50);
    await page.getByRole('combobox', { name: /^Section/ }).selectOption('current'); assert(!new URL(page.url()).searchParams.has('packet_cursor')); await page.getByText('CLANGD-D42', { exact: true }).first().waitFor(); assert.equal(await page.locator('.packet-items > li').count(), 1);
    await page.getByRole('button', { name: 'Back to comparison', exact: true }).click(); await page.getByRole('button', { name: 'Swap sides', exact: true }).click(); await sourceA(page).getByText('SRC-Retry', { exact: true }).waitFor(); await sourceB(page).getByText('L-0000', { exact: true }).waitFor();
  });
  for (const [name, text, status] of [['missing', 'No selection explanation supplied.', 0], ['partial', 'Incomplete supplied evidence references.', 0], ['unknown', 'FUTURE_STATUS', 0], ['contradictory', 'RECEIPT-CONTRADICTORY', 0], ['malformed', 'Receipt binding mismatch', 0], ['denied', 'Access unavailable (403)', 403], ['historical-unavailable', 'Not found (404)', 404]]) await check(`${name} states`, 'http', async (page, base) => {
    await page.goto(base + storyLink + '&investigation_case=' + name);
    await sourceA(page).getByText('SRC-Removal', { exact: true }).waitFor();
    if (status) { await sourceB(page).getByText(text, { exact: true }).waitFor(); assert.equal(await sourceB(page).getByText('fictional-model', { exact: true }).count(), 0); return; }
    await sourceB(page).getByText('SRC-Retry', { exact: true }).waitFor();
    if (name === 'unknown') {
      await page.getByText(text, { exact: true }).waitFor();
      await page.getByRole('tab', { name: 'References', exact: true }).click();
      await page.getByRole('button', { name: 'Inspect PKT-Retry', exact: true }).click();
      await page.getByText('FUTURE_DISPOSITION', { exact: true }).waitFor();
      await page.getByRole('tab', { name: 'Selection & budget', exact: true }).click();
      await page.getByText('FUTURE_EXPLANATION', { exact: true }).waitFor();
      await page.getByRole('tab', { name: 'Receipts', exact: true }).click();
      await page.getByText('FUTURE_RECEIPT', { exact: true }).waitFor();
      await page.getByText('RECEIPT-Retry-PREP', { exact: true }).waitFor(); return;
    }
    await page.getByRole('tab', { name: 'References', exact: true }).click();
    if (name === 'partial') {
      await page.getByText(text, { exact: true }).waitFor();
      await page.getByRole('button', { name: 'Inspect PKT-Retry', exact: true }).click();
      await page.locator('.packet-items').getByText('OMITTED', { exact: true }).waitFor();
      await page.getByText('Supplied excerpt is truncated.', { exact: true }).waitFor();
      await page.getByRole('tab', { name: 'Receipts', exact: true }).click();
      await page.getByText(/Receipt projection is incomplete/).waitFor(); return;
    }
    await page.getByRole('button', { name: 'Inspect PKT-Retry', exact: true }).click();
    if (name === 'missing') await page.getByRole('tab', { name: 'Selection & budget', exact: true }).click();
    if (name === 'contradictory') await page.getByRole('tab', { name: 'Receipts', exact: true }).click();
    await page.getByText(text, { exact: name !== 'malformed' }).first().waitFor();
  }, { expected: status ? [{ path: '/api/preview/investigation/v0.1/sources/SRC-Retry', case: name, status }] : [] });
  await check('hostile excerpts, dark theme, 200 percent text zoom and keyboard tabs', 'http', async (page, base, requests) => {
    await page.goto(base + storyLink + '&investigation_case=hostile&compare_tab=references'); await page.getByRole('button', { name: 'Inspect PKT-Retry', exact: true }).click(); await page.getByText('Safe supplied excerpt', { exact: true }).waitFor();
    assert.equal(await page.evaluate(() => globalThis.w04Attack), undefined); assert(!requests.some(r => r.url.includes('attacker.invalid')));
    await page.getByRole('tab', { name: 'Contents', exact: true }).focus(); await page.keyboard.press('End'); assert.equal(await page.getByRole('tab', { name: 'Provenance', exact: true }).getAttribute('aria-selected'), 'true');
    await page.evaluate(() => { document.documentElement.style.zoom = '2'; }); assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth), false); await page.screenshot({ path: `${out}/dark-zoom.png`, fullPage: true });
  }, { dark: true, phone: true });
  await check('304 metadata and hidden current-source polling', 'http', async (page, base, requests) => {
    await page.goto(base + '/compare?fixture=F1&a_source=SRC-Removal&b_source=CURRENT-INV-0001&compare_tab=references'); await sourceB(page).getByText('CURRENT-INV-0001', { exact: true }).waitFor();
    await sourceA(page).getByText('SRC-Removal', { exact: true }).waitFor();
    const fixedReads = requests.filter(r => r.url.includes('/sources/SRC-Removal')).length;
    await page.evaluate(() => window.dispatchEvent(new window.Event('focus')));
    await page.waitForTimeout(200);
    assert.equal(requests.filter(r => r.url.includes('/sources/SRC-Removal')).length, fixedReads);
    await sourceA(page).getByRole('button', { name: 'Refresh A', exact: true }).click(); await page.waitForFunction(() => document.querySelector('[aria-label="Source A"] time') !== null);
    await page.getByRole('button', { name: 'Inspect PKT-Removal', exact: true }).click(); await page.getByText('Mistaken hypothesis: missing index references suggest dead code.', { exact: true }).waitFor();
    const count = requests.filter(r => r.url.includes('/sources/CURRENT-INV-0001')).length; await page.waitForTimeout(11000); assert.equal(requests.filter(r => r.url.includes('/sources/CURRENT-INV-0001')).length, count);
    assert(requests.some(r => r.url.includes('/sources/SRC-Removal') && r.etag));
  });
  await check('failed refresh retains marked valid data', 'http', async (page, base) => { await page.goto(base + storyLink + '&investigation_case=refresh-error'); await sourceB(page).getByText('SRC-Retry', { exact: true }).waitFor(); await sourceB(page).getByRole('button', { name: 'Refresh B', exact: true }).click(); await sourceB(page).getByRole('status').filter({ hasText: 'STALE / DISCONNECTED' }).waitFor(); await sourceB(page).getByText('SRC-Retry', { exact: true }).waitFor(); }, { expected: [{ path: '/api/preview/investigation/v0.1/sources/SRC-Retry', case: 'refresh-error', status: 500 }] });
  await check('malformed historical link sends no preview reads', 'http', async (page, base, requests) => { await page.goto(base + storyLink + '&revision=old'); await page.getByText('Historical snapshot reads are not supported by this contract.', { exact: true }).waitFor(); assert.equal(requests.filter(r => r.url.includes('/api/preview/investigation/')).length, 0); });
  await check('late old-source response cannot replace new selection; other side remains stable', 'http', async (page, base, requests) => {
    let release;
    const gate = new Promise(resolve => { release = resolve; });
    await page.route('**/api/preview/investigation/v0.1/sources/SRC-Removal?**', async route => { const response = await route.fetch(); await gate; await route.fulfill({ response }); });
    await page.goto(base + storyLink); await sourceB(page).getByText('SRC-Retry', { exact: true }).waitFor();
    const rightReads = requests.filter(r => r.url.includes('/sources/SRC-Retry')).length;
    await choose(page, 'A', 'SRC-Later'); release(); await page.waitForTimeout(250);
    await sourceA(page).getByText('SRC-Later', { exact: true }).waitFor(); assert.equal(await sourceA(page).getByText('CLANGD-INV-Removal', { exact: true }).count(), 0);
    assert.equal(requests.filter(r => r.url.includes('/sources/SRC-Retry')).length, rightReads);
  });
  await check('changed fixed snapshot is rejected before display', 'http', async (page, base) => {
    let reads = 0;
    await page.route('**/api/preview/investigation/v0.1/sources/SRC-Retry?**', async route => { const response = await route.fetch(), body = await response.json(); if (++reads > 1) body.data.snapshot_id = 'WRONG-SNAPSHOT'; await route.fulfill({ response, json: body }); });
    await page.goto(base + storyLink); await sourceB(page).getByText(/Source snapshot\/visibility binding mismatch/).waitFor(); assert.equal(await sourceB(page).getByText('WRONG-SNAPSHOT', { exact: true }).count(), 0);
  });
  await check('access refusal clears one side while retaining the other', 'http', async (page, base) => {
    await page.goto(base + storyLink); await sourceA(page).getByText('SRC-Removal', { exact: true }).waitFor(); await sourceB(page).getByText('SRC-Retry', { exact: true }).waitFor();
    await page.route('**/api/preview/investigation/v0.1/sources/SRC-Removal?**', route => route.fulfill({ status: 403, body: '' }));
    await sourceA(page).getByRole('button', { name: 'Refresh A', exact: true }).click(); await sourceA(page).getByText('Access unavailable (403)', { exact: true }).waitFor(); assert.equal(await sourceA(page).getByText('CLANGD-INV-Removal', { exact: true }).count(), 0); await sourceB(page).getByText('SRC-Retry', { exact: true }).waitFor();
  }, { expected: [{ path: '/api/preview/investigation/v0.1/sources/SRC-Removal', case: 'story', status: 403 }] });
  await check('Work and invocation entry points carry explicit identities', 'http', async (page, base) => {
    await page.goto(base + '/runs/INV-0001?fixture=F1'); await page.getByRole('link', { name: 'Compare invocations', exact: true }).click(); await page.getByText('Starting invocation:', { exact: false }).waitFor(); await page.getByRole('button', { name: 'Select CURRENT-INV-0001 for A', exact: true }).click(); await sourceA(page).getByText('INV-0001', { exact: true }).waitFor();
    await page.goto(base + '/work/T-0001?fixture=F1'); await page.getByRole('link', { name: 'Compare invocations', exact: true }).click(); assert.equal(new URL(page.url()).searchParams.get('compare_work'), 'T-0001'); await page.getByRole('button', { name: 'Select CURRENT-INV-0001 for A', exact: true }).waitFor();
  });
  await check('two agents retain explicit work and starting-context identities', 'http', async (page, base) => {
    await page.goto(base + storyLink + '&investigation_case=parallel');
    await page.getByText(/A second agent investigated the same work/).waitFor();
    await page.getByRole('tab', { name: 'Configuration', exact: true }).click();
    await page.getByText('fictional-model-B', { exact: true }).waitFor();
    await page.getByText('stale-db-fictional', { exact: true }).waitFor();
    await page.getByText('refreshed-db-fictional', { exact: true }).waitFor();
  });
  await check('empty source chooser gives an explicit recoverable result', 'http', async (page, base) => {
    await page.goto(base + '/compare?fixture=F1&investigation_case=empty&choose=a');
    await page.getByText('No comparison sources supplied for this filter.', { exact: true }).waitFor();
    await page.getByRole('button', { name: 'Close source chooser', exact: true }).click();
    await page.waitForFunction(() => document.activeElement?.textContent === 'Change A');
  });
  fs.writeFileSync(`${out}/result.json`, JSON.stringify({ checks, measurements, independent_review: 'PENDING; implementer checks do not substitute for reviewer task completion.' }, null, 2) + '\n');
} finally { await browser?.close(); for (const child of children) child.kill('SIGTERM'); }
