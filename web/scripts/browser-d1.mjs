import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const base = process.env.DASHBOARD_PREVIEW_URL ?? 'http://127.0.0.1:4173';
const out = 'output/playwright-d1';
fs.mkdirSync(out, { recursive: true });
const manifest = JSON.parse(
  fs.readFileSync('node_modules/playwright-core/browsers.json', 'utf8'),
);
const revision = manifest.browsers.find(
  (x) => x.name === 'chromium',
).revision;
const browserPath = path.resolve(
  `artifacts/playwright/browsers/chromium-${revision}/chrome-linux64/chrome`,
);
const browser = await chromium.launch({
  executablePath: browserPath,
  headless: true,
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
});
const page = await context.newPage();
const errors = [];
const expectedNetworkErrors = [];
let faultScenario = false;
const remote = [];
const writes = [];
page.on('pageerror', (e) => errors.push(e.message));
page.on('console', (msg) => {
  if (msg.type() === 'error') {
    if (
      faultScenario &&
      msg.text() ===
        'Failed to load resource: the server responded with a status of 500 (Internal Server Error)'
    )
      expectedNetworkErrors.push(msg.text());
    else errors.push(msg.text());
  }
});
context.on('request', (r) => {
  if (!r.url().startsWith(base + '/') && !r.url().startsWith('data:'))
    remote.push(r.url());
  if (r.url().includes('/api/v1/') && !['GET', 'HEAD'].includes(r.method()))
    writes.push(r.method());
});
const checks = [];
try {
  const response = await page.goto(base + '/?fixture=F1');
  const demoHeaders = response.headers();
  assert(
    demoHeaders['content-security-policy'].includes("style-src 'self'"),
  );
  assert(!demoHeaders['content-security-policy'].includes('unsafe-inline'));
  await page.getByRole('status').filter({ hasText: 'CURRENT' }).waitFor();
  assert(await page.getByText('Demo data', { exact: true }).isVisible());
  await page.getByLabel('Appearance').selectOption('light');
  assert.equal(
    await page.evaluate(
      () => getComputedStyle(document.body).backgroundColor,
    ),
    'rgb(245, 247, 250)',
  );
  await page.screenshot({
    path: out + '/overview-light.png',
    fullPage: true,
  });
  checks.push('compiled Overview, light theme, CSP');
  await page.getByLabel('Appearance').selectOption('dark');
  assert.equal(
    await page.evaluate(
      () => getComputedStyle(document.body).backgroundColor,
    ),
    'rgb(22, 27, 34)',
  );
  await page.screenshot({
    path: out + '/overview-dark.png',
    fullPage: true,
  });
  checks.push('dark theme');
  await page
    .getByRole('link', {
      name: 'Validate projection consistency',
      exact: true,
    })
    .click();
  await page
    .getByRole('heading', {
      name: 'Validate projection consistency',
      exact: true,
    })
    .waitFor();
  await page.reload();
  await page
    .getByRole('heading', {
      name: 'Validate projection consistency',
      exact: true,
    })
    .waitFor();
  await page.screenshot({ path: out + '/ticket-dark.png', fullPage: true });
  checks.push('opaque Ticket deep link and reload');
  await page.goto(base + '/?fixture=F1');
  await page.getByRole('status').filter({ hasText: 'CURRENT' }).waitFor();
  await page.keyboard.press('Tab');
  assert.equal(
    await page.evaluate(() => document.activeElement.textContent),
    'Skip to content',
  );
  await page.keyboard.press('Enter');
  assert.equal(
    await page.evaluate(() => document.activeElement.id),
    'content',
  );
  checks.push('keyboard skip navigation');
  await page.setViewportSize({ width: 390, height: 844 });
  assert(await page.getByLabel('Toggle navigation').isVisible());
  assert(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  );
  await page.getByLabel('Toggle navigation').click();
  assert(
    await page
      .getByRole('navigation', { name: 'Main navigation' })
      .isVisible(),
  );
  await page.getByRole('link', { name: 'Overview', exact: true }).click();
  await page.screenshot({
    path: out + '/overview-phone.png',
    fullPage: true,
  });
  checks.push('phone navigation and panel-confined table overflow');
  await page.goto(base + '/work/T-0001?fixture=F8');
  await page
    .getByRole('heading', {
      name: 'Validate projection consistency',
      exact: true,
    })
    .waitFor();
  assert.equal(
    await page.locator('main script, main img, main iframe').count(),
    0,
  );
  assert.equal(
    await page.locator('main a[href^="javascript:"]').count(),
    0,
  );
  assert.equal(await page.evaluate(() => window.pwned), undefined);
  assert(
    (await page.locator('pre code').textContent()).includes(
      '<script>alert(1)</script>',
    ),
  );
  checks.push(
    'hostile Markdown escaped, raw HTML and remote images suppressed under CSP',
  );
  await page.goto(base + '/?fixture=F11');
  await page.getByText('FUTURE_WORK_STATE', { exact: true }).waitFor();
  await page.getByText('future_projection', { exact: true }).waitFor();
  checks.push('unknown state and capability-key warnings');
  await page.goto(base + '/work/T-0004?fixture=F3');
  await page
    .getByRole('heading', {
      name: 'Archived projection contract',
      exact: true,
    })
    .waitFor();
  await page
    .getByText(
      'Archived work. Historical reference; never current evidence.',
      {
        exact: true,
      },
    )
    .waitFor();
  await page.reload();
  await page
    .getByRole('heading', {
      name: 'Archived projection contract',
      exact: true,
    })
    .waitFor();
  checks.push(
    'archived work by ID, deep-link reload and historical-reference warning',
  );
  faultScenario = true;
  await page.goto(base + '/?fixture=F11&fault=refresh-error');
  await page
    .getByRole('status')
    .filter({ hasText: 'STALE / DISCONNECTED' })
    .waitFor();
  assert(await page.getByRole('table').first().isVisible());
  checks.push('failed refresh retains visibly stale data');
  await page.goto(base + '/?fixture=F10&fault=malformed');
  await page.getByRole('alert').waitFor();
  assert(await page.getByText('LOAD ERROR', { exact: true }).isVisible());
  checks.push('initial malformed-response error');
  assert.deepEqual(errors, []);
  assert.deepEqual(remote, []);
  assert.deepEqual(writes, []);
  checks.push(
    'no unexpected console/page errors, remote subresource requests or API writes',
  );
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(base + '/work?fixture=F1&view=tree');
  await page
    .getByRole('button', {
      name: 'Collapse Explain evidence and execution',
    })
    .click();
  assert.equal(
    await page
      .getByRole('link', {
        name: 'Validate projection consistency',
        exact: true,
      })
      .count(),
    0,
  );
  await page
    .getByRole('button', { name: 'Expand Explain evidence and execution' })
    .click();
  await page
    .getByRole('link', {
      name: 'Validate projection consistency',
      exact: true,
    })
    .waitFor();
  await page.screenshot({ path: out + '/work-tree.png', fullPage: true });
  checks.push('bounded page hierarchy expansion/collapse');
  await page.goto(base + '/work?fixture=F3&state=DONE');
  await page
    .getByRole('link', { name: 'Finished check 28', exact: true })
    .waitFor();
  checks.push('explicit terminal filter reaches older archived work');
  await page.goto(base + '/work?fixture=F6');
  await page
    .getByRole('link', { name: 'Projection check 1', exact: true })
    .waitFor();
  assert((await page.getByRole('row').count()) < 30);
  const viewport = page.getByLabel('Work rows');
  assert((await viewport.evaluate((el) => el.scrollHeight)) > 3000);
  await viewport.focus();
  await page.keyboard.press('End');
  await page
    .getByRole('link', { name: 'Projection check 100', exact: true })
    .waitFor();
  assert((await page.getByRole('row').count()) < 30);
  await page.getByRole('checkbox').check();
  assert.equal(await page.getByRole('row').count(), 101);
  await page
    .getByRole('button', { name: 'Next page', exact: true })
    .click();
  await page
    .getByRole('link', { name: 'Projection check 101', exact: true })
    .waitFor();
  await page.screenshot({
    path: out + '/work-large-page.png',
    fullPage: true,
  });
  checks.push(
    'CSP-safe measured virtualization, keyboard scroll, accessible row view, opaque cursor pagination',
  );
  await page.goto(base + '/work/T-1145?fixture=F6');
  await page
    .getByRole('heading', { name: 'Projection check 146', exact: true })
    .waitFor();
  await page.reload();
  await page
    .getByRole('heading', { name: 'Projection check 146', exact: true })
    .waitFor();
  checks.push('large-page arbitrary work detail and deep-link reload');
  await page.goto(base + '/queue?fixture=F1');
  await page
    .getByRole('heading', { name: 'Data unavailable', exact: true })
    .waitFor();
  checks.push(
    'unsupported queue explanation with no invented wire request',
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(base + '/work?fixture=F6');
  await page
    .getByRole('link', { name: 'Projection check 1', exact: true })
    .waitFor();
  assert(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  );
  await page.screenshot({ path: out + '/work-phone.png', fullPage: true });
  checks.push('phone work table confines overflow to panel');
  const productionBase =
    process.env.DASHBOARD_PRODUCTION_URL ?? 'http://127.0.0.1:4175';
  const pc = await browser.newContext();
  const pp = await pc.newPage();
  const requests = [];
  pp.on('request', (r) =>
    requests.push({ url: r.url(), method: r.method() }),
  );
  pp.on('pageerror', (e) => errors.push(e.message));
  pp.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  const pr = await pp.goto(productionBase);
  await pp.getByRole('status').filter({ hasText: 'CURRENT' }).waitFor();
  await pp
    .getByRole('link', {
      name: 'Validate projection consistency',
      exact: true,
    })
    .click();
  await pp
    .getByRole('heading', {
      name: 'Validate projection consistency',
      exact: true,
    })
    .waitFor();
  await pp.reload();
  await pp
    .getByRole('heading', {
      name: 'Validate projection consistency',
      exact: true,
    })
    .waitFor();
  assert.equal(await pp.getByText('Demo data', { exact: true }).count(), 0);
  assert.equal(
    await pp.evaluate(
      async () => (await navigator.serviceWorker.getRegistrations()).length,
    ),
    0,
  );
  assert(requests.some((r) => r.url.includes('/api/v1/work/T-0001')));
  assert(
    requests.every(
      (r) =>
        r.url.startsWith(productionBase + '/') &&
        !r.url.includes('mockServiceWorker') &&
        ['GET', 'HEAD'].includes(r.method),
    ),
  );
  const productionHeaders = pr.headers();
  assert(
    productionHeaders['content-security-policy'].includes(
      "style-src 'self'",
    ),
  );
  assert.deepEqual(errors, []);
  assert.deepEqual(remote, []);
  assert.deepEqual(writes, []);
  await pc.close();
  checks.push(
    'production API-driven Overview/detail reload through test-only fixture adapter, no worker/demo/remote/writes',
  );
  fs.writeFileSync(
    out + '/browser-d1.json',
    JSON.stringify(
      {
        status: 'PASS',
        playwright: '1.59.1',
        chromium_revision: revision,
        browser_version: browser.version(),
        base,
        checks,
        errors,
        expected_network_errors: expectedNetworkErrors,
        remote,
        writes,
        scope:
          'D1 Overview/Work only; test adapter is fixture-backed, no live Engine integration; D2-D4 pending visual review',
      },
      null,
      2,
    ) + '\n',
  );
  console.log(JSON.stringify({ status: 'PASS', checks }, null, 2));
} finally {
  await browser.close();
}
