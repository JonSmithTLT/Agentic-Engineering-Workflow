import { spawn } from 'node:child_process';
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const out = process.env.HTTP_DEMO_OUTPUT ?? 'output/playwright-http-demo';
const port = process.env.HTTP_DEMO_PORT ?? '4254', base = `http://127.0.0.1:${port}`;
fs.mkdirSync(out, {recursive: true});
const log = fs.openSync(`${out}/server.log`, 'w');
const server = spawn(process.execPath, ['--experimental-strip-types', 'scripts/demo-server.mjs'], {env: {...process.env, DASHBOARD_PORT: port}, stdio: ['ignore', log, log]});
const checks = [];
let browser;
async function ready() {
  for (let i = 0; i < 100; i++) {
    if (server.exitCode !== null) throw new Error('Owned HTTP fixture server exited');
    try { if ((await globalThis.fetch(base)).ok) return; } catch { /* owned startup */ }
    await new Promise(r => globalThis.setTimeout(r, 100));
  }
  throw new Error('HTTP fixture server did not start');
}
async function check(name, viewport, run) {
  const context = await browser.newContext({viewport, serviceWorkers: 'block'});
  const page = await context.newPage(), errors = [], failures = [], requests = [];
  await context.tracing.start({screenshots: true, snapshots: true});
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('response', r => { if (r.status() >= 400) failures.push({url: r.url(), status: r.status()}); });
  page.on('request', r => requests.push(r.url()));
  try {
    await run(page, requests);
    assert.deepEqual(errors, []); assert.deepEqual(failures, []);
    assert(!requests.some(url => /mockServiceWorker|assets\/browser-/.test(url)), 'No worker adapter import or registration');
    assert.equal(context.serviceWorkers().length, 0);
    checks.push({name, result: 'PASS'}); console.log('PASS ' + name);
    await context.tracing.stop();
  } catch (error) {
    await page.screenshot({path: `${out}/failure-${checks.length}.png`, fullPage: true});
    await context.tracing.stop({path: `${out}/failure-${checks.length}.zip`}); throw error;
  } finally { await context.close(); }
}
try {
  await ready();
  browser = await chromium.launch({executablePath: process.env.CHROMIUM_PATH ?? path.resolve('artifacts/playwright/browsers/chromium-1217/chrome-linux64/chrome')});
  await check('HTTP demo loads requested screens without blocking the surrounding shell', {width: 1092, height: 1000}, async (page, requests) => {
    await page.goto(base + '/overview?fixture=F1');
    await page.getByRole('heading', {name: 'Overview', exact: true}).waitFor();
    assert(!requests.some(url => /\/assets\/(Journal|Recorder|Comparison|Reader|Lab|PacketInspector|BoundPacketHost)-/.test(url)), 'Overview does not load unrelated investigation UI');
    let release;
    const held = new Promise(resolve => { release = resolve; });
    await page.route('**/assets/Journal-*.js', async route => { await held; await route.continue(); });
    try {
      await page.getByRole('link', {name: 'Knowledge', exact: true}).click();
      await page.getByRole('status').filter({hasText: 'Opening Knowledge Journal…'}).waitFor();
      assert(await page.getByRole('button', {name: 'API panel', exact: true}).isVisible());
      assert(!requests.some(url => url.includes('/api/preview/journal/')), 'Concealed, unloaded screen has no preview reads');
    } finally { release(); }
    await page.getByRole('heading', {name: 'Knowledge Journal', exact: true}).waitFor();
    assert(!requests.some(url => /\/assets\/(Recorder|Comparison|Reader|Lab)-/.test(url)));
    await page.getByRole('button', {name: 'API panel', exact: true}).click();
    await page.getByRole('heading', {name: 'API requests', exact: true}).waitFor();
    assert(!requests.some(url => /\/assets\/Lab-/.test(url)), 'Requests disclosure needs no Playground UI');
    await page.getByRole('tab', {name: 'Contract', exact: true}).click();
    await page.getByRole('heading', {name: 'Contract Playground', exact: true}).waitFor();
    assert(requests.some(url => /\/assets\/Lab-/.test(url)), 'Explicit Contract disclosure loads the Playground');
  });
  for (const phone of [false, true]) await check(`${phone ? 'phone' : 'desktop'} HTTP investigation, selection, legend, focus and graph`, {width: phone ? 390 : 1440, height: phone ? 844 : 1000}, async page => {
    await page.goto(base + '/knowledge?fixture=F1');
    await page.locator('.header-tools').getByText('HEALTHY', {exact: true}).waitFor();
    const entry = page.locator('.journal-results [data-journal-id="J-05"]');
    await entry.focus(); await page.keyboard.press('Enter');
    const detail = page.locator('.journal-detail');
    await detail.getByRole('heading', {name: /J-05 · Refresh/}).waitFor();
    await page.evaluate(() => new Promise(resolve => globalThis.requestAnimationFrame(() => globalThis.requestAnimationFrame(resolve))));
    if (phone) {
      assert(await detail.locator('h2').evaluate(el => el === document.activeElement), 'Phone results selection focuses the replacing detail');
    } else {
      assert(await entry.evaluate(el => el === document.activeElement), 'Desktop list selection retains focus');
      await page.keyboard.press('Shift+Tab');
      assert.notEqual(await page.evaluate(() => document.activeElement?.getAttribute('data-journal-id')), 'J-07');
      await page.keyboard.press('Tab');
      assert(await entry.evaluate(el => el === document.activeElement), 'Sequential focus returns to selected entry');
    }
    await page.getByText('Knowledge type legend', {exact: false}).click();
    assert.equal(await page.locator('.journal-legend .journal-kind-mark').count(), 7);
    await page.getByText('Knowledge type legend', {exact: false}).click();
    if (phone) {
      await page.getByRole('button', {name: 'Results', exact: true}).click();
      assert.equal(await page.getByRole('button', {name: 'Results', exact: true}).getAttribute('aria-pressed'), 'true');
      assert(await page.locator('.workspace-selection').getByText('J-05', {exact: true}).isVisible());
      assert(await page.getByRole('button', {name: 'Detail', exact: true}).getByText('J-05').isVisible());
      await page.getByRole('button', {name: 'Detail', exact: true}).click();
      assert.equal(await page.getByRole('button', {name: 'Detail', exact: true}).getAttribute('aria-pressed'), 'true');
    }
    const sequence = [['J-02 · related_to', 'J-02'], ['J-03 · contradicted_by', 'J-03'], ['J-04 · followed_by', 'J-04'], ['J-05 · contributed_to', 'J-05']];
    for (const [link, id] of sequence) {
      await page.getByRole('tab', {name: 'Provenance', exact: true}).click();
      await detail.getByRole('link', {name: link, exact: true}).click();
      await page.waitForFunction(id => document.activeElement?.tagName === 'H2' && document.activeElement.textContent.startsWith(id + ' ·'), id);
      const heading = detail.getByRole('heading', {name: new RegExp('^' + id + ' ·')});
      assert(await heading.isVisible());
      if (phone) assert(await heading.evaluate(el => el.getBoundingClientRect().top > document.querySelector('.project-header').getBoundingClientRect().bottom));
    }
    await page.getByRole('tab', {name: 'Evidence', exact: true}).click();
    for (const id of ['CLANGD-E871', 'CLANGD-E875', 'CLANGD-E880']) await detail.getByText(id, {exact: true}).waitFor();
    await page.getByRole('tab', {name: 'Provenance', exact: true}).click();
    await detail.getByText('CLANGD-D42', {exact: true}).waitFor();
    await detail.getByText('Explore bounded origin graph', {exact: true}).click();
    await page.getByRole('button', {name: 'Expand J-05', exact: true}).click();
    await page.getByRole('button', {name: 'Expand J-04', exact: true}).waitFor();
    assert(await page.locator('.provenance-node').filter({hasText: 'J-04'}).getByText('journal · not expanded', {exact: true}).isVisible());
    const rows = await page.locator('.graph-edge-list li').evaluateAll(nodes => nodes.map(n => n.getBoundingClientRect().toJSON()));
    assert(rows.length > 1 && rows[1].top > rows[0].bottom, 'Source rows have space');
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({path: `${out}/${phone ? 'phone' : 'desktop'}.png`, fullPage: true});
  });
  await check('HTTP fixture switching, accepted Records, large paging and conditional reads', {width: 1440, height: 1000}, async (page, requests) => {
    await page.goto(base + '/knowledge?fixture=F1&view=records');
    await page.locator('.knowledge-group').first().waitFor();
    assert(!requests.some(url => url.includes('/api/preview/journal')));
    await page.getByRole('combobox', {name: 'Demo scenario'}).selectOption('F2');
    await page.waitForURL(/fixture=F2/);
    await page.getByRole('heading', {name: 'Knowledge', exact: true}).waitFor();
    await page.goto(base + '/knowledge?fixture=F1&journal_case=large');
    await page.locator('.journal-item').first().waitFor();
    assert.equal(await page.locator('.journal-item').count(), 50);
    const first = await page.locator('[data-journal-id]').first().getAttribute('data-journal-id');
    await page.getByRole('button', {name: 'Next page', exact: true}).click();
    await page.waitForFunction(id => { const entries = document.querySelectorAll('.journal-item [data-journal-id]'); return entries.length === 50 && entries[0].getAttribute('data-journal-id') !== id; }, first);
    const conditional = await page.evaluate(async () => {
      const url = '/api/preview/journal/v0.1/entries/J-05?case=story';
      const first = await globalThis.fetch(url); const tag = first.headers.get('ETag');
      const second = await globalThis.fetch(url, {method: 'HEAD', headers: {'If-None-Match': tag}});
      return {first: first.status, second: second.status, tag: second.headers.get('ETag'), original: tag};
    });
    assert.equal(conditional.first, 200); assert.equal(conditional.second, 304); assert.equal(conditional.tag, conditional.original);
  });
  await check('desktop keyboard position survives stream and table selections on a 50-entry page', {width: 1440, height: 1000}, async page => {
    await page.goto(base + '/knowledge?fixture=F1&journal_case=large');
    for (const display of ['stream', 'table']) {
      await page.getByLabel('Display', {exact: true}).selectOption(display);
      const links = page.locator('.journal-results [data-journal-id]');
      await links.nth(25).waitFor();
      const previous = await links.nth(24).getAttribute('data-journal-id');
      const entry = links.nth(25), id = await entry.getAttribute('data-journal-id');
      await entry.focus(); await page.keyboard.press('Enter');
      await page.locator('.journal-detail h2').filter({hasText: id + ' ·'}).waitFor();
      await page.evaluate(() => new Promise(resolve => globalThis.requestAnimationFrame(() => globalThis.requestAnimationFrame(resolve))));
      assert(await entry.evaluate(el => el === document.activeElement));
      await page.keyboard.press('Shift+Tab');
      assert.equal(await page.evaluate(() => document.activeElement?.getAttribute('data-journal-id')), previous);
      await page.keyboard.press('Tab');
      assert(await entry.evaluate(el => el === document.activeElement));
      assert.equal(await page.locator('.workspace-selection').getAttribute('role'), 'status');
    }
  });
  await check('phone Work child selection and history restore visible focus without a service worker', {width:390, height:844}, async page => {
    await page.goto(base + '/work?fixture=F1&selected=S-0001');
    await page.getByRole('link', {name:'Inspect children',exact:true}).click();
    const results = page.getByRole('region', {name:'Investigation results',exact:true});
    const child = results.getByRole('link', {name:'Validate projection consistency',exact:true});
    await child.waitFor();
    // Inspect children restores Results focus after history scroll restoration.
    // Finish that navigation before testing the next keyboard action.
    await page.waitForFunction(() => document.activeElement?.tagName === 'H1' && document.activeElement?.textContent === 'Work');
    await page.evaluate(() => window.scrollTo(0,652));
    await child.focus(); await page.keyboard.press('Enter');
    await page.waitForFunction(() => document.activeElement?.getAttribute('data-work-heading') === 'T-0001');
    const visibleFocus = () => page.evaluate(() => {
      const rect = document.activeElement.getBoundingClientRect();
      return rect.top >= (document.querySelector('.project-header')?.getBoundingClientRect().bottom ?? 0) && rect.bottom <= window.innerHeight;
    });
    assert(await visibleFocus(), 'Detail heading is visible after selecting a child from scrolled Results');
    await page.screenshot({path:`${out}/work-density-phone-detail-focus.png`});
    await page.goBack();
    await page.waitForFunction(() => document.activeElement?.tagName === 'A' && document.activeElement?.textContent === 'Validate projection consistency');
    assert(await visibleFocus(), 'Back restores the visible child link after native history scroll restoration');
    await page.screenshot({path:`${out}/work-density-phone-back-focus.png`});
    await page.goForward();
    await page.waitForFunction(() => document.activeElement?.getAttribute('data-work-heading') === 'T-0001');
    assert(await visibleFocus());
    await page.getByRole('button', {name:'Results',exact:true}).click();
    await page.waitForFunction(() => document.activeElement?.tagName === 'H1' && document.activeElement?.textContent === 'Work');
    await page.getByRole('button', {name:'Detail',exact:true}).click();
    await page.waitForFunction(() => document.activeElement?.getAttribute('data-work-heading') === 'T-0001');
    assert(await visibleFocus(), 'Switching back to the same selected detail also restores visible heading focus');
  });
  fs.writeFileSync(`${out}/result.json`, JSON.stringify({checks, service_workers: 'BLOCKED', browser: browser.version(), independent_review: 'fixing-diff re-check pending'}, null, 2) + '\n');
} finally {
  if (browser) await browser.close(); server.kill('SIGTERM'); fs.closeSync(log);
}
