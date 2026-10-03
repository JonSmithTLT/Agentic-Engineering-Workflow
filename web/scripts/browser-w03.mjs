import { spawn } from 'node:child_process';
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const out = process.env.W03_BROWSER_OUTPUT ?? 'output/playwright-w03';
const port = process.env.W03_DEMO_PORT ?? '4240', base = `http://127.0.0.1:${port}`;
fs.mkdirSync(out, { recursive: true });
const log = fs.openSync(`${out}/server.log`, 'w');
const server = spawn(process.execPath, ['node_modules/vite/bin/vite.js', 'preview', '--mode', 'demo', '--host', '127.0.0.1', '--port', port, '--strictPort'], { stdio: ['ignore', log, log] });
let browser, active;
const checks = [], measurements = [], taskRuns = [];
async function ready() {
  for (let i = 0; i < 100; i++) {
    if (server.exitCode !== null) throw new Error('Owned demo server exited');
    try { if ((await globalThis.fetch(base)).ok) return; } catch { /* Owned startup. */ }
    await new Promise((r) => globalThis.setTimeout(r, 100));
  }
  throw new Error('Demo server did not start');
}
async function check(name, fn, options = {}) {
  const context = await browser.newContext({ viewport: options.viewport ?? { width: 1440, height: 1000 }, permissions: ['clipboard-read', 'clipboard-write'], colorScheme: options.dark ? 'dark' : 'light' });
  active = context;
  await context.tracing.start({ screenshots: true, snapshots: true, sources: true });
  const page = await context.newPage(), errors = [], failures = [], requests = [];
  const expected = options.expected ?? [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => {
    if (m.type() !== 'error') return;
    if (/Failed to load resource/.test(m.text()) && expected.some((f) => m.location().url === base + f.path)) return;
    errors.push(m.text());
  });
  page.on('response', (r) => { if (r.status() >= 400 && !expected.some((f) => r.url() === base + f.path && r.status() === f.status)) failures.push({ url: r.url(), status: r.status() }); });
  page.on('request', (r) => requests.push({ url: r.url(), method: r.method() }));
  try {
    await fn(page, requests);
    assert.deepEqual(errors, [], `${name}: unexpected console/page errors`);
    assert.deepEqual(failures, [], `${name}: unexpected HTTP failure`);
    assert(requests.every((r) => ['GET', 'HEAD'].includes(r.method)), 'Read-only requests');
    checks.push({ name, result: 'PASS' }); console.log('PASS ' + name);
    await context.tracing.stop();
  } catch (error) {
    await page.screenshot({ path: `${out}/failure-${checks.length}.png`, fullPage: true }).catch(() => {});
    await context.tracing.stop({ path: `${out}/failure-${checks.length}.zip` });
    throw error;
  } finally { await context.close(); active = undefined; }
}
async function open(page, query = '') {
  const start = Date.now();
  await page.goto(`${base}/knowledge?fixture=F1${query}`);
  await page.getByRole('heading', { name: 'Knowledge Journal', exact: true }).waitFor();
  await page.locator('.header-tools').getByText('HEALTHY', { exact: true }).waitFor();
  return start;
}
const selected = () => '&selected=J-05';
async function investigation(page, phone) {
  await open(page, selected());
  const detail = page.locator('.journal-detail');
  await detail.getByText('Conditional lesson: refresh the compilation database before using missing clangd references as evidence that a function is unused.').waitFor();
  const steps = [];
  const tab = async (name) => { await page.getByRole('tab', { name, exact: true }).click(); await page.locator(`#journal-panel-${name.toLowerCase()}`).waitFor({ state: 'visible' }); };
  await tab('Provenance');
  await detail.getByRole('link', { name: 'J-02 · related_to', exact: true }).click();
  await detail.getByText('Mistaken hypothesis: missing index references were interpreted as absence of callers.').waitFor(); steps.push({ entry: 'J-02', established: 'mistaken hypothesis' });
  await tab('Provenance'); await detail.getByRole('link', { name: 'J-03 · contradicted_by', exact: true }).click();
  await detail.getByText(/Failed removal: deleting the function/).waitFor(); steps.push({ entry: 'J-03', established: 'failed removal' });
  await tab('Provenance'); await detail.getByRole('link', { name: 'J-04 · followed_by', exact: true }).click();
  await detail.getByText(/New discovery: refreshed compile_commands/).waitFor(); steps.push({ entry: 'J-04', established: 'discovery' });
  await tab('Provenance'); await detail.getByRole('link', { name: 'J-05 · contributed_to', exact: true }).click();
  await detail.getByText(/Conditional lesson: refresh the compilation database/).waitFor(); steps.push({ entry: 'J-05', established: 'conditional lesson' });
  await tab('Evidence');
  await detail.getByText('CLANGD-E871', { exact: true }).waitFor();
  assert(await detail.getByText('CLANGD-E871', { exact: true }).isVisible());
  assert(await detail.getByText('CLANGD-E875', { exact: true }).isVisible());
  assert(await detail.getByText('CLANGD-E880', { exact: true }).isVisible());
  steps.push({ established: 'explicit supporting/opposing roles', supporting: ['CLANGD-E871', 'CLANGD-E875'], opposing: ['CLANGD-E880'] });
  await tab('Provenance'); await detail.getByText('CLANGD-D42', { exact: true }).waitFor(); assert(await detail.getByText('CLANGD-D42', { exact: true }).isVisible());
  steps.push({ established: 'canonical reference, no second authority', reference: 'CLANGD-D42' });
  assert(!(await page.locator('.developer-panel').count()), 'No developer tools needed');
  if (phone) {
    await page.getByRole('button', { name: 'Stream', exact: true }).click();
    assert(!(await detail.isVisible()));
    await page.getByRole('button', { name: 'Detail', exact: true }).click();
    assert(await detail.isVisible());
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `${out}/investigation-${phone ? 'phone' : 'desktop'}.png`, fullPage: true });
  taskRuns.push({ layout: phone ? 'phone' : 'desktop', performer: 'implementer automation, independent review still pending', steps, developer_tools_used: false, fixture_source_used: false, result: 'PASS' });
}
try {
  await ready();
  browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? path.resolve('artifacts/playwright/browsers/chromium-1217/chrome-linux64/chrome') });
  await check('desktop fictional investigation via UI', (page) => investigation(page, false));
  await check('phone fictional investigation via UI', (page) => investigation(page, true), { viewport: { width: 390, height: 844 } });
  await check('selection, filters, table, copy and reload', async (page) => {
    await open(page, selected()); await page.locator('.journal-detail').getByText(/Conditional lesson:/).waitFor();
    await page.getByLabel('Component', { exact: true }).selectOption('missing');
    await page.getByText('Selected entry is outside these results. Its detail remains selected.').waitFor();
    assert(await page.locator('.journal-detail').isVisible());
    await page.getByLabel('Display', { exact: true }).selectOption('table');
    await page.locator('.journal-results tbody tr').first().waitFor();
    assert.equal(await page.locator('.journal-results tbody tr').count(), 1);
    await page.getByRole('tab', { name: 'Evidence' }).click();
    await page.getByRole('button', { name: 'Copy dashboard link', exact: true }).click();
    const copied = await page.evaluate(() => navigator.clipboard.readText());
    assert(copied.includes('component_missing=1') && copied.includes('selected=J-05') && copied.includes('panel=evidence') && copied.includes('display=table'));
    await page.reload(); await page.getByRole('tab', { name: 'Evidence' }).waitFor();
    assert.equal(await page.getByRole('tab', { name: 'Evidence' }).getAttribute('aria-selected'), 'true');
  });
  await check('keyboard tabs, graph/list, partiality and close focus', async (page) => {
    await open(page, selected()); const summary = page.getByRole('tab', { name: 'Summary' }); await summary.waitFor();
    await summary.focus(); await page.keyboard.press('End');
    await page.waitForFunction(() => document.querySelector('#journal-tab-provenance')?.getAttribute('aria-selected') === 'true');
    assert.equal(await page.getByRole('tab', { name: 'Provenance' }).getAttribute('aria-selected'), 'true');
    await page.getByText('Explore bounded origin graph', { exact: true }).click();
    await page.getByRole('button', { name: 'Expand J-05', exact: true }).click();
    await page.getByRole('button', { name: 'Expand J-04', exact: true }).click();
    assert(await page.getByText(/Absence of a relationship is not evidence/).isVisible());
    await page.getByRole('button', { name: 'Fit to width', exact: true }).click();
    await page.getByRole('button', { name: 'Show relation list', exact: true }).click();
    await page.locator('.relation-list button').first().click();
    await page.getByText('Supplied edge source', { exact: true }).waitFor();
    assert((await page.locator('.provenance-node').count()) <= 24);
    await page.getByRole('button', { name: 'Close detail', exact: true }).click();
    await page.waitForFunction(() => document.activeElement?.getAttribute('data-journal-id') === 'J-05');
  });
  await check('missing, stale, contradictory and unknown supplied values', async (page) => {
    for (const name of ['missing', 'stale', 'contradictory', 'unknown']) {
      await open(page, selected() + '&journal_case=' + name);
      const detail = page.locator('.journal-detail'); await detail.getByRole('tab', { name: 'Summary' }).waitFor();
      if (name === 'missing') { await detail.getByText('No retention explanation supplied.', { exact: true }).waitFor(); await page.getByRole('tab', { name: 'Evidence' }).click(); await detail.getByText('No opposing evidence references supplied.').waitFor(); }
      if (name === 'stale') await detail.getByText('STALE FOR ENVIRONMENT', { exact: true }).waitFor();
      if (name === 'contradictory') await detail.getByText('CONTRADICTORY', { exact: true }).waitFor();
      if (name === 'unknown') await detail.getByText(/FUTURE_APPLICABILITY/).waitFor();
    }
  });
  await check('malformed, denied and missing initial projections', async (page) => {
    for (const name of ['malformed', 'denied', 'not-found']) {
      await open(page, '&journal_case=' + name);
      await page.locator('.journal-results [role=alert]').waitFor();
      assert.equal(await page.locator('.journal-stream .journal-item').count(), 0);
    }
  }, { expected: [{ path: '/api/preview/journal/v0.1/entries?case=denied&limit=50', status: 403 }, { path: '/api/preview/journal/v0.1/entries?case=not-found&limit=50', status: 404 }] });
  await check('graph caps and omissions stay explicit', async (page) => {
    await open(page, selected() + '&journal_case=bounds&panel=provenance');
    await page.getByText('Explore bounded origin graph', { exact: true }).click();
    await page.getByRole('button', { name: 'Expand J-05', exact: true }).click();
    await page.waitForFunction(() => document.querySelectorAll('.provenance-node').length === 24);
    assert.equal(await page.locator('.provenance-node').count(), 24);
    assert.equal(await page.locator('.provenance-plane svg line').count(), 80);
    await page.getByText(/supplied references omitted from this graph/).waitFor();
    await page.getByRole('button', { name: 'Show relation list' }).click();
    await page.waitForFunction(() => document.querySelectorAll('.relation-list li').length === 100);
    await page.getByRole('button', { name: 'Next relations' }).click();
    assert((await page.locator('.relation-list li').count()) <= 100);
  });
  await check('refresh failure preserves explicitly stale content', async (page) => {
    await open(page, '&journal_case=refresh-error'); await page.locator('.journal-item').first().waitFor();
    // Real visibility revalidation uses W01's shared listener, not a synthetic API call.
    await page.evaluate(() => window.dispatchEvent(new globalThis.Event('focus')));
    await page.getByText(/Last known valid journal retained; refresh failed/).waitFor();
    assert.equal(await page.locator('.journal-item').count(), 7);
  }, { expected: [{ path: '/api/preview/journal/v0.1/entries?case=refresh-error&limit=50', status: 500 }] });
  await check('hostile Markdown, dark theme and zoom/reflow', async (page, requests) => {
    await open(page, selected() + '&journal_case=hostile'); await page.getByText('Safe retained text', { exact: true }).waitFor();
    assert.equal(await page.evaluate(() => globalThis.journalAttack), undefined);
    assert(!requests.some((r) => r.url.includes('attacker.invalid')));
    assert.equal(await page.locator('.journal-detail img').count(), 0);
    await page.setViewportSize({ width: 720, height: 500 });
    const size = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth, scrollbar: getComputedStyle(document.documentElement).scrollbarColor }));
    assert(size.scroll <= size.width + 1, 'Overflow remains panel-owned at effective 200% desktop reflow');
    assert.notEqual(size.scrollbar, 'auto');
    await page.screenshot({ path: `${out}/dark-reflow.png`, fullPage: true });
  }, { dark: true });
  await check('phone concealed detail stops polling and revalidates on reveal', async (page, requests) => {
    await open(page, selected()); await page.locator('.journal-detail').getByRole('tab', { name: 'Summary' }).waitFor();
    await page.getByRole('button', { name: 'Stream', exact: true }).click();
    await page.locator('.journal-detail').waitFor({ state: 'hidden' });
    const reads = () => requests.filter((r) => r.url.includes('/api/preview/journal/v0.1/entries/J-05')).length;
    const before = reads();
    await page.waitForTimeout(11000); // Observe the existing ten-second polling cadence.
    assert.equal(reads(), before, 'No concealed detail interval reads');
    const revalidated = page.waitForResponse((r) => r.url().includes('/api/preview/journal/v0.1/entries/J-05'));
    await page.getByRole('button', { name: 'Detail', exact: true }).click();
    await revalidated;
    assert(reads() > before);
  }, { viewport: { width: 390, height: 844 } });
  await check('large fixture pages and bounded requests', async (page, requests) => {
    const start = await open(page, '&journal_case=large'); await page.locator('.journal-item').first().waitFor();
    assert.equal(await page.locator('.journal-item').count(), 50);
    const first = await page.locator('[data-journal-id]').first().getAttribute('data-journal-id');
    await page.getByRole('button', { name: 'Next page', exact: true }).click();
    await page.waitForFunction((id) => {
      const entries = document.querySelectorAll('.journal-item [data-journal-id]');
      return entries.length === 50 && entries[0].getAttribute('data-journal-id') !== id;
    }, first);
    assert.equal(await page.locator('.journal-item').count(), 50);
    measurements.push({ name: 'journal large 10000 entries', navigate_and_page_ms: Date.now() - start, mounted_entries: 50, journal_requests: requests.filter((r) => r.url.includes('/api/preview/')).length, all_requests: requests.length, dom_nodes: await page.locator('*').count() });
  });
  await check('accepted Records remains available and historical scope is honest', async (page, requests) => {
    await page.goto(`${base}/knowledge?fixture=F1&view=records`); await page.getByRole('heading', { name: 'Knowledge', exact: true }).waitFor(); await page.locator('.knowledge-group').first().waitFor();
    assert(!requests.some((r) => r.url.includes('/api/preview/')));
    await page.goto(`${base}/knowledge?fixture=F1&rev=41`); await page.getByText('Historical snapshot reads are not supported by this contract.').waitFor();
    assert(!requests.some((r) => r.url.includes('/api/preview/')));
  });
  fs.writeFileSync(`${out}/result.json`, JSON.stringify({ checks, measurements, taskRuns, browser: browser.version(), independent_review: 'PENDING' }, null, 2) + '\n');
} finally {
  if (active) await active.close();
  if (browser) await browser.close();
  server.kill('SIGTERM');
  fs.closeSync(log);
}
