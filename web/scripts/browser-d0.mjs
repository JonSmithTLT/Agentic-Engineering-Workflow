import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const base = process.env.DASHBOARD_PREVIEW_URL ?? 'http://127.0.0.1:4173';
const out = 'output/playwright';
fs.mkdirSync(out, { recursive: true });
const manifest = JSON.parse(
  fs.readFileSync('node_modules/playwright-core/browsers.json', 'utf8'),
);
const revision = manifest.browsers.find(
  (x) => x.name === 'chromium',
).revision;
const browserPath =
  process.env.CHROMIUM_PATH ??
  path.resolve(
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
  if (process.env.DASHBOARD_PRODUCTION_URL) {
    const productionBase = process.env.DASHBOARD_PRODUCTION_URL;
    const pc = await browser.newContext();
    const pp = await pc.newPage();
    const requests = [];
    pp.on('request', (r) => requests.push(r.url()));
    pp.on('pageerror', (e) => errors.push(e.message));
    const response = await pp.goto(productionBase);
    await pp
      .getByRole('heading', { name: 'AEW dashboard foundation' })
      .waitFor();
    await pp.waitForLoadState('networkidle');
    assert(!(await pp.getByText('Demo data', { exact: true }).count()));
    assert.equal(
      await pp.evaluate(
        async () =>
          (await navigator.serviceWorker.getRegistrations()).length,
      ),
      0,
    );
    assert(
      requests.every(
        (url) =>
          url.startsWith(productionBase + '/') &&
          !url.includes('/api/v1/') &&
          !url.includes('mockServiceWorker'),
      ),
    );
    const productionHeaders = response.headers();
    assert(
      productionHeaders['content-security-policy'].includes(
        "script-src 'self'",
      ),
    );
    assert.deepEqual(errors, []);
    await pc.close();
    checks.push(
      'compiled production shell: no fixtures, worker registration, API calls or remote assets',
    );
  }
  fs.writeFileSync(
    out + '/browser-d0.json',
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
          'D0 shell/provisional previews only; D1-D4 and integration not covered',
      },
      null,
      2,
    ) + '\n',
  );
  console.log(JSON.stringify({ status: 'PASS', checks }, null, 2));
} finally {
  await browser.close();
}
