import { spawn } from 'node:child_process';
import fs from 'node:fs';
import assert from 'node:assert/strict';
import { URL } from 'node:url';
import { chromium } from 'playwright';
const output = process.env.SETTINGS_OUTPUT ?? 'output/playwright-settings';
fs.mkdirSync(output, { recursive: true });
const ports = { worker: process.env.SETTINGS_WORKER_PORT ?? '4410', http: process.env.SETTINGS_HTTP_PORT ?? '4411' };
const owned = [], results = [];
let browser;
function server(adapter) {
  const log = fs.openSync(`${output}/${adapter}-server.log`, 'w');
  const child = spawn(process.execPath, adapter === 'http' ? ['--experimental-strip-types', 'scripts/demo-server.mjs'] : ['node_modules/vite/bin/vite.js', 'preview', '--mode', 'demo', '--host', '127.0.0.1', '--port', ports.worker, '--strictPort'], { env: { ...process.env, DASHBOARD_PORT: ports.http }, stdio: ['ignore', log, log] });
  owned.push(child); return child;
}
async function ready(base, child) {
  for (let i = 0; i < 100; i++) { if (child.exitCode !== null) throw new Error('Owned Settings server exited'); try { if ((await globalThis.fetch(base)).ok) return; } catch { /* startup */ } await new Promise(resolve => globalThis.setTimeout(resolve, 100)); }
  throw new Error('Settings server did not start');
}
try {
  browser = await chromium.launch({ headless: true, ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}) });
  for (const adapter of ['worker', 'http']) {
    const base = `http://127.0.0.1:${ports[adapter]}`, child = server(adapter); await ready(base, child);
    for (const width of [1440, 390, 720]) {
      const context = await browser.newContext({ viewport: { width, height: 900 }, serviceWorkers: adapter === 'http' ? 'block' : 'allow', permissions: ['clipboard-read', 'clipboard-write'] });
      const page = await context.newPage(), errors = [], configurationReads = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('request', request => { if (new URL(request.url()).pathname.includes('/configuration')) configurationReads.push(request.url()); });
      await context.tracing.start({ screenshots: true, snapshots: true });
      try {
        await page.goto(`${base}/settings?fixture=F1`);
        await page.getByRole('button', { name: 'standard', exact: true }).click();
        await page.getByRole('heading', { name: 'Profile standard', exact: true }).waitFor();
        assert.equal(await page.getByText('Configured null (NULL)', { exact: true }).count(), 1);
        if (width < 1024) assert.equal(await page.evaluate(() => document.activeElement?.textContent), 'Profile standard');
        else assert.equal(await page.evaluate(() => document.activeElement?.textContent), 'standard');
        for (const theme of ['light', 'dark']) {
          const appearance = page.getByLabel('Appearance', { exact: true });
          const revealNavigation = !await appearance.isVisible();
          if (revealNavigation) await page.getByRole('button', { name: 'Toggle navigation', exact: true }).click();
          await appearance.selectOption(theme);
          if (revealNavigation) {
            await page.getByRole('button', { name: 'Close navigation', exact: true }).click();
            assert.equal(await page.getByRole('button', { name: 'Toggle navigation', exact: true }).getAttribute('aria-expanded'), 'false');
            assert.equal(await page.evaluate(() => document.activeElement?.getAttribute('aria-label')), 'Toggle navigation');
          }
          await page.screenshot({ path: `${output}/${adapter}-${width}-${theme}-profile.png`, fullPage: true });
          assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'No viewport overflow');
        }
        await page.getByRole('tab', { name: 'Profiles', exact: true }).focus(); await page.keyboard.press('End');
        assert.equal(await page.evaluate(() => document.activeElement?.id), 'settings-execution-tab-controls');
        await page.getByText('Supplied effective mode', { exact: true }).waitFor();
        await page.getByText('3600', { exact: true }).waitFor();
        await page.getByRole('tab', { name: 'Providers', exact: true }).click();
        await page.getByText('EXAMPLE_PROVIDER_KEY', { exact: true }).waitFor();
        await page.getByText(/Named by the policy \(not per provider\)/).waitFor();
        await page.getByRole('tab', { name: 'Providers', exact: true }).focus(); await page.keyboard.press('End');
        await page.getByRole('heading', { name: 'Project', exact: true }).waitFor();
        assert.equal(await page.evaluate(() => document.activeElement?.id), 'settings-tab-project');
        await page.keyboard.press('Home'); await page.getByRole('heading', { name: 'Controls', exact: true }).waitFor();
        await page.getByRole('tab', { name: 'Profiles', exact: true }).click();
        await page.getByRole('heading', { name: 'Profiles', exact: true }).waitFor();
        assert.equal(await page.getByRole('tab', { name: 'Profiles', exact: true }).getAttribute('aria-selected'), 'true');
        await page.getByRole('combobox', { name: 'Settings scenario', exact: true }).selectOption('withheld');
        await page.getByRole('button', { name: 'Profile 1 (name withheld)', exact: true }).click();
        await page.getByText('field withheld', { exact: true }).waitFor();
        await page.getByRole('button', { name: 'Copy dashboard link', exact: true }).click();
        await page.getByText('Dashboard link copied.', { exact: true }).waitFor();
        const copied = await page.evaluate(() => navigator.clipboard.readText());
        assert.equal(new URL(copied).searchParams.get('settings_profile'), '1');
        assert.equal(new URL(copied).searchParams.get('settings_digest'), `sha256:${'a'.repeat(64)}`);
        await page.goto(copied); await page.getByRole('heading', { name: 'Profile 1 (name withheld)', exact: true }).waitFor();
        for (const [scenario, text] of [['drifted', /On-disk configuration is drifted/], ['unpin', /Never adopted/], ['manifest', /Manifest drifted/], ['invalid', /Configuration is invalid/], ['absent', /Configuration is absent/], ['empty', 'No profiles supplied.'], ['partial', 'Profile list is truncated. Additional entries are not listed.'], ['unknown', /Unknown value: FUTURE_DOCUMENT_STATE/], ['error', 'Synthetic configuration read failed.']]) {
          await page.getByRole('combobox', { name: 'Settings scenario', exact: true }).selectOption(scenario);
          const owner = scenario === 'unknown' ? page.locator('.settings-page > section.settings-panel') : page;
          await owner.getByText(text, { exact: typeof text === 'string' }).waitFor();
        }
        await page.getByRole('combobox', { name: 'Settings scenario', exact: true }).selectOption('long');
        await page.getByText(/<script>window.__settingsHostile=1<\/script>/).waitFor();
        assert.equal(await page.evaluate(() => window.__settingsHostile), undefined);
        assert.equal(await page.locator('.settings-page script').count(), 0);
        await page.screenshot({ path: `${output}/${adapter}-${width}-long.png`, fullPage: true });
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'Long content stays bounded');
        await page.goto(`${base}/settings?fixture=F1&settings_activity=arbitrary`);
        await page.getByText('Unsupported Settings presentation link. No configuration data was read.', { exact: true }).waitFor();
        assert.deepEqual(configurationReads, [], 'No speculative configuration routes'); assert.deepEqual(errors, []);
        results.push({ adapter, width, result: 'PASS', zoom: width === 720 ? 'narrow reflow proxy, not real browser zoom' : 'not tested', configurationReads: configurationReads.length });
      } finally { await context.tracing.stop({ path: `${output}/${adapter}-${width}.zip` }); await context.close(); }
    }
  }
  fs.writeFileSync(`${output}/results.json`, JSON.stringify(results, null, 2));
  console.log('Settings compiled worker/HTTP checks PASS', results);
} finally { await browser?.close(); for (const child of owned) child.kill(); }
