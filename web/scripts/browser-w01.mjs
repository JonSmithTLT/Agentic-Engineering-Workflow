import { URL } from 'node:url';
import { performance } from 'node:perf_hooks';
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const base = process.env.DASHBOARD_PREVIEW_URL ?? 'http://127.0.0.1:4191';
const production =
  process.env.DASHBOARD_PRODUCTION_URL ?? 'http://127.0.0.1:4192';
const baseline = process.env.DASHBOARD_BASELINE_URL;
const out = process.env.W01_BROWSER_OUTPUT ?? 'output/playwright-w01';
fs.mkdirSync(out, { recursive: true });
const revision = JSON.parse(
  fs.readFileSync('node_modules/playwright-core/browsers.json', 'utf8'),
).browsers.find((b) => b.name === 'chromium').revision;
const browser = await chromium.launch({
  executablePath:
    process.env.PLAYWRIGHT_BROWSER_EXECUTABLE ??
    path.resolve(
      `artifacts/playwright/browsers/chromium-${revision}/chrome-linux64/chrome`,
    ),
});
const checks = [],
  errors = [],
  requests = [],
  failures = [],
  measurements = [];
let expectedFailure = false;
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  permissions: ['clipboard-read', 'clipboard-write'],
});
await context.tracing.start({
  screenshots: true,
  snapshots: true,
  sources: true,
});
const page = await context.newPage();
page.on('pageerror', (e) => errors.push(e.message));
page.on('console', (m) => {
  if (m.type() === 'error' && !expectedFailure) errors.push(m.text());
});
page.on('request', (r) => {
  requests.push({ url: r.url(), method: r.method() });
});
page.on('response', (r) => {
  if (r.status() >= 400)
    failures.push({
      url: r.url(),
      status: r.status(),
      expected: expectedFailure,
    });
});
async function panel(tab) {
  const trigger = page.getByRole('button', { name: 'API panel', exact: true });
  if ((await trigger.getAttribute('aria-expanded')) !== 'true')
    await trigger.click();
  await page.getByRole('tab', { name: tab, exact: true }).click();
}
async function replay(
  id,
  { error = false, route = '/work', fixture = 'F1' } = {},
) {
  expectedFailure = error;
  await page.goto(
    `${base}${route}?catalog=1.0.0&recipe=${id}&fixture=${fixture}&seed=17`,
  );
  await panel('Scenarios');
  await page.getByRole('status').filter({ hasText: 'Manual replay' }).waitFor();
}
async function next() {
  await page.getByRole('button', { name: 'Next step', exact: true }).click();
}
async function screenshot(name) {
  await page.screenshot({ path: `${out}/${name}.png`, fullPage: true });
}
async function check(name, fn) {
  await fn();
  checks.push({ name, result: 'PASS' });
  console.log(`PASS ${name}`);
}
try {
  await check(
    'Demo tabs, keyboard focus, bounded contract diagnostics and safe input',
    async () => {
      await page.goto(base + '/work?fixture=F1');
      await page.getByRole('heading', { name: 'Work records' }).waitFor();
      await page
        .getByRole('button', { name: 'API panel', exact: true })
        .click();
      const requestsTab = page.getByRole('tab', {
        name: 'Requests',
        exact: true,
      });
      await requestsTab.focus();
      await page.keyboard.press('ArrowRight');
      assert.equal(
        await page
          .getByRole('tab', { name: 'Scenarios', exact: true })
          .getAttribute('aria-selected'),
        'true',
      );
      await page.keyboard.press('End');
      await page.getByLabel('Response schema').selectOption('WorkResponse');
      await page
        .getByRole('button', { name: 'Load fixture', exact: true })
        .click();
      await page.getByRole('button', { name: 'Validate', exact: true }).click();
      await page.getByText('Accepted shape', { exact: true }).waitFor();
      const value = JSON.parse(
        await page.getByLabel('Response JSON').inputValue(),
      );
      value.data.state = 'W01_FUTURE_STATE';
      await page.getByLabel('Response JSON').fill(JSON.stringify(value));
      await page.getByRole('button', { name: 'Validate', exact: true }).click();
      await page
        .getByText('Accepted shape; unknown semantic values', { exact: true })
        .waitFor();
      await page.getByLabel('Response JSON').fill('{"bad":true}');
      await page.getByRole('button', { name: 'Validate', exact: true }).click();
      await page.getByText('Invalid shape', { exact: true }).waitFor();
      assert(
        await page
          .getByRole('tabpanel', { name: 'Contract' })
          .getByText('project_id', { exact: true })
          .count(),
      );
      await screenshot('contract-light');
      await page.getByLabel('Appearance').selectOption('dark');
      await screenshot('contract-dark');
      await page.keyboard.press('Escape');
      await page
        .getByRole('button', { name: 'API panel', exact: true })
        .evaluate((e) => {
          if (e !== document.activeElement)
            throw new Error('Focus did not return to API panel trigger');
        });
    },
  );
  await check(
    'Conditional recheck preserves generation and exposes 304',
    async () => {
      await replay('conditional');
      await page.getByRole('heading', { name: 'Work records' }).waitFor();
      await next();
      await panel('Requests');
      await page.getByText('304', { exact: true }).first().waitFor();
      await panel('Scenarios');
      await page.getByRole('button', { name: 'Reset', exact: true }).click();
      await page.getByRole('status').filter({ hasText: 'step 0/1' }).waitFor();
      await screenshot('scenario-replay');
    },
  );
  await check(
    'Failed/malformed refresh retains content and recovers',
    async () => {
      await replay('failed-refresh', { error: true });
      await page.getByRole('heading', { name: 'Work records' }).waitFor();
      await next();
      await page.getByText('STALE / DISCONNECTED', { exact: true }).waitFor();
      await next();
      await panel('Requests');
      await page
        .getByText('Response validation failed', { exact: true })
        .first()
        .waitFor();
      await panel('Scenarios');
      await next();
      await page.getByText('CURRENT', { exact: true }).waitFor();
    },
  );
  await check(
    'Initial 304, HTTP and network errors have no stale data',
    async () => {
      for (const id of ['initial-304', 'initial-http', 'initial-network']) {
        await replay(id, { error: true });
        assert.equal(
          await page.getByRole('heading', { name: 'Work records' }).count(),
          0,
        );
        assert.equal(
          await page.getByText('STALE / DISCONNECTED', { exact: true }).count(),
          0,
        );
        await next();
        await page.getByRole('heading', { name: 'Work records' }).waitFor();
      }
    },
  );
  await check('Mismatched ETag is an observation', async () => {
    await replay('validator');
    await page.getByRole('heading', { name: 'Work records' }).waitFor();
    await next();
    await panel('Requests');
    await page.getByText('ETag observation', { exact: true }).first().waitFor();
  });
  await check(
    'Persistent divergence pauses hidden and clears on convergence',
    async () => {
      await replay('persistent-mixed');
      await page.getByRole('heading', { name: 'Work records' }).waitFor();
      await next();
      await page.getByText('UPDATING', { exact: true }).waitFor();
      for (let i = 0; i < 4; i++) await next();
      assert.equal(
        await page
          .locator('.snapshot')
          .getByText(/Mixed revisions persist/)
          .count(),
        0,
      );
      await next();
      await page
        .locator('.snapshot')
        .getByText(/Mixed revisions persist/)
        .waitFor();
      await next();
      await page.getByText('CURRENT', { exact: true }).waitFor();
    },
  );
  await check(
    'Transient revisions converge without persistent warning',
    async () => {
      await replay('transient-mixed');
      await page.getByRole('heading', { name: 'Work records' }).waitFor();
      await next();
      await page.getByText('UPDATING', { exact: true }).waitFor();
      await next();
      await next();
      await page.getByText('CURRENT', { exact: true }).waitFor();
      assert.equal(
        await page
          .locator('.snapshot')
          .getByText(/Mixed revisions persist/)
          .count(),
        0,
      );
    },
  );
  await check(
    'Capability downgrade suppresses subsequent Work reads',
    async () => {
      await replay('capability');
      await page.getByRole('heading', { name: 'Work records' }).waitFor();
      await next();
      await page.getByText(/Authored fixture downgrade/).waitFor();
      const count = requests.filter(
        (r) => new URL(r.url).pathname === '/api/v1/work',
      ).length;
      await next();
      await page.getByRole('status').filter({ hasText: 'step 2/2' }).waitFor();
      assert.equal(
        requests.filter((r) => new URL(r.url).pathname === '/api/v1/work')
          .length,
        count,
      );
    },
  );
  await check(
    'Retired held response cannot reappear in a new project',
    async () => {
      await replay('late-session');
      await page.getByRole('heading', { name: 'Work records' }).waitFor();
      await next();
      await page.getByRole('button', { name: /Release response/ }).waitFor();
      await next();
      await page.getByText('demo-aew-other', { exact: true }).waitFor();
      await page.getByRole('button', { name: /Release response/ }).click();
      await next();
      await page.getByText('CURRENT', { exact: true }).waitFor();
      await panel('Requests');
      assert.equal(
        await page.getByText('project:demo/aew', { exact: true }).count(),
        0,
      );
    },
  );
  await check('Unknown strings remain raw warnings', async () => {
    await replay('unknown');
    await page.getByRole('heading', { name: 'Work records' }).waitFor();
    await next();
    await page.getByText('W01_FUTURE_STATE', { exact: true }).waitFor();
  });
  await check('Graph navigation and reload retain replay context', async () => {
    await page.goto(base + '/work?fixture=F1&view=graph');
    await page.getByRole('button', { name: /Select S-0001:/ }).waitFor();
    await page.getByRole('button', { name: 'Fit width', exact: true }).click();
    const canvas = page.getByLabel('Work graph canvas');
    const bounds = await canvas.boundingBox();
    const old = await page
      .locator('.graph-surface')
      .evaluate((e) => e.style.transform);
    await page.mouse.move(bounds.x + 50, bounds.y + 10);
    await page.mouse.down();
    await page.mouse.move(bounds.x + 120, bounds.y + 30, { steps: 6 });
    await page.mouse.up();
    assert.notEqual(
      await page.locator('.graph-surface').evaluate((e) => e.style.transform),
      old,
    );
    await page.goto(
      base + '/work/S-0001?catalog=1.0.0&recipe=conditional&fixture=F1&seed=17',
    );
    await page.getByText('S-0001', { exact: true }).first().waitFor();
    await page.reload();
    assert(new URL(page.url()).searchParams.has('recipe'));
  });
  await check(
    'Hostile display and phone panel are safe under CSP',
    async () => {
      await page.goto(base + '/work/T-0001?fixture=F8');
      await page.getByRole('heading').first().waitFor();
      assert.equal(
        await page.locator('main img,main script,main iframe').count(),
        0,
      );
      await page.setViewportSize({ width: 390, height: 844 });
      await panel('Contract');
      await screenshot('contract-phone');
      assert(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth + 1,
        ),
      );
      await page.setViewportSize({ width: 1440, height: 1000 });
    },
  );
  await check(
    'Normal production excludes lab and works with storage blocked',
    async () => {
      const prodContext = await browser.newContext({ serviceWorkers: 'block' });
      await prodContext.addInitScript(() => {
        Object.defineProperty(window, 'localStorage', {
          get() {
            throw new Error('Blocked storage');
          },
        });
      });
      const p = await prodContext.newPage();
      await p.goto(production + '/work');
      await p.getByRole('heading', { name: 'Work records' }).waitFor();
      await p.getByRole('button', { name: 'API panel', exact: true }).click();
      assert.equal(await p.getByRole('tab').count(), 0);
      assert.equal(await p.getByText('Demo data', { exact: true }).count(), 0);
      await prodContext.close();
    },
  );
  await check(
    'Ordinary polling pauses hidden and immediately revalidates on visibility restoration',
    async () => {
      expectedFailure = false;
      await page.goto(base + '/work?fixture=F1');
      await page.getByRole('heading', { name: 'Work records' }).waitFor();
      const count = () =>
        requests.filter((r) => new URL(r.url).pathname === '/api/v1/overview')
          .length;
      const first = count();
      await page.waitForTimeout(2200);
      assert(count() > first);
      await page.evaluate(() => {
        Object.defineProperty(document, 'visibilityState', {
          configurable: true,
          value: 'hidden',
        });
        document.dispatchEvent(new window.Event('visibilitychange'));
      });
      await page.waitForTimeout(100);
      const hiddenCount = count();
      await page.waitForTimeout(5200);
      assert.equal(count(), hiddenCount);
      await page.evaluate(() => {
        Object.defineProperty(document, 'visibilityState', {
          configurable: true,
          value: 'visible',
        });
        document.dispatchEvent(new window.Event('visibilitychange'));
      });
      await page.waitForTimeout(200);
      assert(count() > hiddenCount);
    },
  );
  await check(
    'Large worlds stay bounded; baseline comparison recorded',
    async () => {
      for (const [fixture, route] of [
        ['F6', '/work'],
        ['F7', '/history'],
      ])
        for (const [label, url] of [
          ['candidate', base],
          ...(baseline ? [['baseline', baseline]] : []),
        ]) {
          const p = await context.newPage();
          let api = 0;
          p.on('request', (r) => {
            if (new URL(r.url()).pathname.startsWith('/api/v1')) api++;
          });
          const start = performance.now();
          await p.goto(`${url}${route}?fixture=${fixture}`);
          await p.locator('tbody tr').first().waitFor();
          const rows = await p.locator('tbody tr').count();
          assert(rows <= 100);
          measurements.push({
            label,
            fixture,
            load_ms: Math.round(performance.now() - start),
            dom_rows: rows,
            api_requests: api,
          });
          await p.close();
        }
    },
  );
  assert.equal(errors.length, 0, JSON.stringify(errors));
  assert(!failures.some((f) => !f.expected), JSON.stringify(failures));
  assert(
    !requests.some(
      (r) =>
        !['GET', 'HEAD'].includes(r.method) &&
        new URL(r.url).pathname.startsWith('/api/v1'),
    ),
  );
  assert(
    !requests.some((r) => /attacker\.invalid|untrusted\.invalid/.test(r.url)),
  );
  await context.tracing.stop();
  fs.writeFileSync(
    `${out}/report.json`,
    JSON.stringify(
      {
        status: 'PASS',
        browser_revision: revision,
        checks,
        errors,
        failures,
        measurements,
      },
      null,
      2,
    ),
  );
} catch (error) {
  await screenshot('failure').catch(() => {});
  await context.tracing
    .stop({ path: `${out}/failure-trace.zip` })
    .catch(() => {});
  fs.writeFileSync(
    `${out}/report.json`,
    JSON.stringify(
      {
        status: 'FAIL',
        message: String(error),
        checks,
        errors,
        failures,
        measurements,
      },
      null,
      2,
    ),
  );
  throw error;
} finally {
  await browser.close();
}
