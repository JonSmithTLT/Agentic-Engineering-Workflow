import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { URL } from 'node:url';
const base = process.env.DASHBOARD_PREVIEW_URL ?? 'http://127.0.0.1:4187',
  out = 'output/playwright-developer-tools';
fs.mkdirSync(out, { recursive: true });
const revision = JSON.parse(
  fs.readFileSync('node_modules/playwright-core/browsers.json'),
).browsers.find((b) => b.name === 'chromium').revision;
const production =
  process.env.DASHBOARD_PRODUCTION_URL ?? 'http://127.0.0.1:4188';
const browser = await chromium.launch({
  executablePath: path.resolve(
    `artifacts/playwright/browsers/chromium-${revision}/chrome-linux64/chrome`,
  ),
});
const failedResponses = [];
const errors = [],
  requests = [],
  checks = [];
function watch(p) {
  p.on('response', (r) => {
    if (r.status() >= 400)
      failedResponses.push({
        url: r.url(),
        status: r.status(),
        page: p.url(),
        worker: r.fromServiceWorker(),
        type: r.headers()['content-type'],
      });
  });
  p.on('pageerror', (e) => errors.push(e.message));
  p.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text());
  });
  p.on('request', (r) => requests.push({ url: r.url(), method: r.method() }));
}
try {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    permissions: ['clipboard-read', 'clipboard-write'],
  });
  const page = await context.newPage();
  watch(page);
  await page.goto(base + '/work?view=graph&fixture=F1');
  await page.getByRole('button', { name: /^Select S-0001:/ }).waitFor();
  await page.getByRole('button', { name: 'Fit width', exact: true }).click();
  const canvas = page.getByLabel('Work graph canvas'),
    bounds = await canvas.boundingBox();
  const before = await page
    .locator('.graph-surface')
    .evaluate((e) => e.style.transform);
  await page.mouse.move(bounds.x + 50, bounds.y + 10);
  await page.mouse.down();
  await page.mouse.move(bounds.x + 120, bounds.y + 30, { steps: 6 });
  await page.mouse.up();
  const after = await page
    .locator('.graph-surface')
    .evaluate((e) => e.style.transform);
  assert.notEqual(after, before);
  assert(after.includes('translate(70px'));
  await page.getByRole('button', { name: 'Reset zoom', exact: true }).click();
  assert(
    (
      await page.locator('.graph-surface').evaluate((e) => e.style.transform)
    ).includes('translate(0px'),
  );
  checks.push('Fit width preserves free drag pan; reset zoom resets pan');
  for (const [id, title] of [
    ['E-0001', 'Observable engineering workflow'],
    ['S-0001', 'Explain evidence and execution'],
    ['T-0001', 'Validate projection consistency'],
  ]) {
    await page.goto(base + '/work?view=graph&fixture=F1');
    await page
      .getByRole('button', { name: new RegExp('^Select ' + id + ':') })
      .click();
    await page
      .getByRole('link', { name: 'Open Work detail', exact: true })
      .click();
    await page.getByRole('heading', { name: title, exact: true }).waitFor();
    await page.reload();
    await page.getByRole('heading', { name: title, exact: true }).waitFor();
  }
  checks.push(
    'Graph Epic, Story and Ticket detail links and reloads return valid records',
  );
  await page
    .getByRole('button', { name: 'Copy read-only CLI for T-0001', exact: true })
    .first()
    .click();
  assert.equal(
    await page.evaluate(() => navigator.clipboard.readText()),
    'aew work show T-0001',
  );
  checks.push(
    'Copy CLI writes the verified read-only command to clipboard only',
  );
  await page.keyboard.press('Control+k');
  await page.getByRole('dialog', { name: 'Jump to an ID' }).waitFor();
  await page.getByLabel('Jump record type').selectOption('invocation');
  await page.getByLabel('Jump record ID').fill('INV-0001');
  await page.getByRole('button', { name: 'Open record', exact: true }).click();
  await page
    .getByRole('heading', { name: 'Harness runs', exact: true })
    .waitFor();
  assert(page.url().includes('/runs/INV-0001?fixture=F1'));
  await page.keyboard.press('Control+k');
  await page.getByLabel('Jump record ID').fill('../bad');
  await page.getByRole('button', { name: 'Open record', exact: true }).click();
  await page.getByText('Enter a URL-safe AEW record ID.').waitFor();
  await page.keyboard.press('Escape');
  checks.push(
    'Keyboard ID jump routes opaque ID by explicit kind; invalid IDs do not navigate',
  );
  await page.getByRole('button', { name: 'API panel', exact: true }).click();
  const panel = page.getByRole('region', { name: 'API developer panel' });
  await panel.waitFor();
  await page.waitForTimeout(2200);
  assert((await panel.locator('summary').count()) > 0);
  assert((await panel.innerText()).includes('304'));
  await panel.locator('summary').first().click();
  await panel
    .locator('details[open]')
    .getByText('Sent If-None-Match', { exact: true })
    .first()
    .waitFor();
  await page.screenshot({ path: out + '/api-panel.png', fullPage: true });
  await page.getByRole('button', { name: 'Close API panel' }).click();
  checks.push(
    'Developer drawer records real 200/304 requests, revision, timing and ETag details',
  );
  await page.goto(base + '/history/T-0004?fixture=F3');
  const lineage = page.locator('.lineage-panel');
  await lineage
    .getByRole('button', { name: 'Expand links', exact: true })
    .waitFor();
  const historyBefore = requests.filter((r) =>
    r.url.includes('/api/v1/history/'),
  ).length;
  await lineage
    .getByRole('button', { name: 'Expand links', exact: true })
    .click();
  assert.equal(await lineage.locator('.lineage-card').count(), 8);
  assert.equal(
    requests.filter((r) => r.url.includes('/api/v1/history/')).length,
    historyBefore,
  );
  await lineage.locator('.lineage-relations summary').click();
  await lineage.getByText('invocations', { exact: true }).waitFor();
  await lineage
    .locator('.lineage-card')
    .filter({ hasText: 'T-0002' })
    .getByRole('button', { name: 'Expand links', exact: true })
    .click();
  await lineage.getByText(/History lookup failed; reference remains/).waitFor();
  await page.evaluate(() => window.scrollTo(0, 0));
  await lineage.locator('.lineage-canvas').evaluate((e) => {
    e.scrollTop = 0;
  });
  await page.screenshot({ path: out + '/lineage.png', fullPage: true });
  checks.push(
    'Historical graph expands backend links on demand; typed terminal links, absent History target remains explicit',
  );
  await page.goto(base + '/work?fixture=F1');
  await page
    .getByRole('heading', { name: 'Work records', exact: true })
    .waitFor();
  await page.evaluate(() => {
    const key = 'aew-dashboard-view-memory-v1',
      views = JSON.parse(window.localStorage.getItem(key) || '[]');
    const view = views.find((v) => v.scope === 'work:/work?limit=100:demo:F1');
    view.revision = '41';
    view.items.find((i) => i.id === 'T-0001').state = 'READY';
    window.localStorage.setItem(key, JSON.stringify(views));
  });
  await page.reload();
  await page.locator('.since-viewed summary').click();
  await page.getByText('READY → RUNNING', { exact: false }).waitFor();
  await page.screenshot({ path: out + '/since-viewed.png', fullPage: true });
  await page.getByRole('button', { name: 'Clear saved comparisons' }).click();
  await page.getByText(/Saved comparisons cleared/).waitFor();
  checks.push(
    'Since-viewed snapshot persists across reload, labels bounded state differences and clears safely',
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(base + '/work?view=graph&fixture=F1');
  await page.getByRole('button', { name: /^Select S-0001:/ }).waitFor();
  assert(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  );
  await page.getByRole('button', { name: 'API panel', exact: true }).click();
  assert(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  );
  await page.screenshot({ path: out + '/tools-phone.png', fullPage: true });
  checks.push(
    'Optional controls and drawer remain usable on phone without page overflow',
  );
  const invalid = await browser.newContext({ serviceWorkers: 'block' });
  const validFixture = JSON.parse(
    fs.readFileSync('src/api/mock/fixtures/F1.json', 'utf8'),
  );
  await invalid.route('**/api/v1/**', async (route) => {
    const pathname = new URL(route.request().url()).pathname.slice(
      '/api/v1'.length,
    );
    assert(
      validFixture.responses[pathname],
      'Unexpected validation probe route ' + pathname,
    );
    const body = JSON.parse(JSON.stringify(validFixture.responses[pathname]));
    if (pathname === '/project') body.data.name = 7;
    await route.fulfill({ json: body });
  });
  const invalidPage = await invalid.newPage();
  watch(invalidPage);
  await invalidPage.goto(production + '/work');
  await invalidPage
    .getByRole('button', { name: 'API panel', exact: true })
    .click();
  const invalidPanel = invalidPage.getByRole('region', {
    name: 'API developer panel',
  });
  await invalidPanel
    .locator('.request-issue summary')
    .filter({ hasText: 'Response validation failed' })
    .first()
    .click();
  await invalidPanel.getByText('data.name', { exact: true }).first().waitFor();
  await invalidPage.screenshot({
    path: out + '/validation-field.png',
    fullPage: true,
  });
  await invalid.close();
  checks.push(
    'Normal production drawer identifies exact malformed response field data.name',
  );
  const blocked = await browser.newContext({ serviceWorkers: 'block' });
  const fixtures = JSON.parse(
    fs.readFileSync('src/api/mock/fixtures/F1.json', 'utf8'),
  );
  await blocked.route('**/api/v1/**', async (route) => {
    const pathname = new URL(route.request().url()).pathname.slice(
      '/api/v1'.length,
    );
    assert(
      fixtures.responses[pathname],
      'Unexpected production route ' + pathname,
    );
    await route.fulfill({ json: fixtures.responses[pathname] });
  });
  await blocked.addInitScript(() => {
    window.Storage.prototype.getItem = function () {
      throw new Error('Storage blocked');
    };
    window.Storage.prototype.setItem = function () {
      throw new Error('Storage blocked');
    };
  });
  const p = await blocked.newPage();
  watch(p);
  await p.goto(production + '/work');
  await p.getByRole('heading', { name: 'Work records', exact: true }).waitFor();
  await p.locator('.since-viewed summary').click();
  await p.getByText(/Browser storage is unavailable/).waitFor();
  await blocked.close();
  checks.push(
    'Normal production build with synthetic API survives blocked storage during bootstrap and Work rendering',
  );
  // Expected 404 is a fixture result, never a browser exception; Chromium may log its HTTP failure.
  assert(
    failedResponses.every(
      (r) => r.status === 404 && r.url.includes('/api/v1/history/T-0002'),
    ),
    JSON.stringify(failedResponses),
  );
  const unexpected = errors.filter((e) => !e.includes('404 (Not Found)'));
  assert.deepEqual(unexpected, []);
  assert(
    !requests.some(
      (r) => r.url.includes('/api/v1/') && !['GET', 'HEAD'].includes(r.method),
    ),
  );
  assert(
    !requests.some(
      (r) =>
        !r.url.startsWith(base + '/') &&
        !r.url.startsWith(production + '/') &&
        !r.url.startsWith('data:'),
    ),
  );
  checks.push(
    'No unexpected browser/CSP errors, remote resources or API writes',
  );
  fs.writeFileSync(
    out + '/browser-developer-tools.json',
    JSON.stringify(
      {
        status: 'PASS',
        checks,
        errors: unexpected,
        expected_http_errors: errors.filter((e) =>
          e.includes('404 (Not Found)'),
        ),
        scope:
          'Compiled optional tools, accepted mock projections; not live integration',
        playwright: '1.59.1',
        chromium_revision: revision,
        browser_version: browser.version(),
      },
      null,
      2,
    ) + '\n',
  );
  console.log(`PASS ${checks.length} developer-tool browser checks`);
  await context.close();
} finally {
  await browser.close();
}
