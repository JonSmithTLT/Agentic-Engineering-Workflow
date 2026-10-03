import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const base = process.env.DASHBOARD_PREVIEW_URL ?? 'http://127.0.0.1:4187';
const out = 'output/playwright-chrome-polish';
fs.mkdirSync(out, { recursive: true });
const revision = JSON.parse(
  fs.readFileSync('node_modules/playwright-core/browsers.json'),
).browsers.find((b) => b.name === 'chromium').revision;
const browser = await chromium.launch({
  executablePath:
    process.env.CHROMIUM_PATH ??
    path.resolve(
      `artifacts/playwright/browsers/chromium-${revision}/chrome-linux64/chrome`,
    ),
});
const checks = [],
  errors = [];
try {
  const p = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  p.on('pageerror', (e) => errors.push(e.message));
  p.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text());
  });
  await p.goto(base + '/queue?fixture=F1');
  await p.getByRole('heading', { name: 'Queue', exact: true }).waitFor();
  const aligned = await p
    .locator(
      '.header-tools > button, .header-tools .world-picker select, .header-tools .header-status',
    )
    .evaluateAll((nodes) =>
      nodes.map((n) => ({
        name: n.textContent,
        top: n.getBoundingClientRect().top,
        height: n.getBoundingClientRect().height,
      })),
    );
  assert(
    Math.max(...aligned.map((n) => n.top)) -
      Math.min(...aligned.map((n) => n.top)) <=
      1,
    JSON.stringify(aligned),
  );
  assert(aligned.every((n) => n.height === 34));
  await p.screenshot({ path: out + '/header-queue.png' });
  checks.push(
    'Scenario dropdown, API panel, ID jump and demo badge share top edge and 34px height',
  );
  await p.setViewportSize({ width: 1280, height: 500 });
  await p.evaluate(() =>
    window.scrollTo(0, document.documentElement.scrollHeight),
  );
  const sidebar = p.locator('.sidebar');
  const bounds = await sidebar.boundingBox();
  assert(bounds.y <= 1 && bounds.y + bounds.height >= 499);
  assert(await sidebar.evaluate((e) => e.scrollHeight > e.clientHeight));
  await sidebar.evaluate((e) => {
    e.scrollTop = e.scrollHeight;
  });
  await p.getByLabel('Appearance').waitFor({ state: 'visible' });
  const appearance = await p.getByLabel('Appearance').boundingBox();
  assert(appearance.y + appearance.height <= 500);
  assert(
    await p.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  );
  await p.screenshot({ path: out + '/short-queue-sidebar.png' });
  checks.push(
    'Short placeholder at 500px height: rail covers viewport, overlong navigation scrolls internally and appearance stays reachable',
  );
  await p.setViewportSize({ width: 1440, height: 900 });
  await p.goto(base + '/history/T-0004?fixture=F3');
  await p
    .getByRole('heading', { name: 'Lineage and links', exact: true })
    .waitFor();
  await p.evaluate(() =>
    window.scrollTo(0, document.documentElement.scrollHeight),
  );
  const long = await sidebar.boundingBox();
  assert(long.y <= 1 && long.y + long.height >= 899);
  await p.screenshot({ path: out + '/long-history-sidebar.png' });
  checks.push('Long History page: sidebar fills viewport at document bottom');
  await p.setViewportSize({ width: 390, height: 500 });
  await p.goto(base + '/queue?fixture=F1');
  await p.getByRole('button', { name: 'Toggle navigation' }).click();
  await sidebar.waitFor({ state: 'visible' });
  await sidebar.evaluate((e) => {
    e.scrollTop = e.scrollHeight;
  });
  const phone = await sidebar.boundingBox();
  assert(phone.y <= 1 && phone.y + phone.height >= 499);
  const phoneAppearance = await p.getByLabel('Appearance').boundingBox();
  assert(phoneAppearance.y + phoneAppearance.height <= 500);
  await p.screenshot({ path: out + '/phone-navigation.png' });
  checks.push(
    'Phone navigation fills viewport and scrolls to its appearance control',
  );
  assert.deepEqual(errors, []);
  fs.writeFileSync(
    out + '/browser-chrome-polish.json',
    JSON.stringify(
      {
        status: 'PASS',
        checks,
        errors,
        scope:
          'Compiled demo CSS geometry under proposed CSP; no live API integration',
      },
      null,
      2,
    ) + '\n',
  );
  console.log(`PASS ${checks.length} chrome layout checks`);
} finally {
  await browser.close();
}
