import { spawn } from 'node:child_process';
import fs from 'node:fs';
const out = process.env.W01_BROWSER_OUTPUT ?? 'output/playwright-w01';
const demoPort = process.env.W01_DEMO_PORT ?? '4191';
const productionPort = process.env.W01_PRODUCTION_PORT ?? '4192';
fs.mkdirSync(out, { recursive: true });
const owned = [];
function server(args, env, file) {
  const log = fs.openSync(`${out}/${file}`, 'w');
  const child = spawn(process.execPath, args, {
    env: { ...process.env, ...env },
    stdio: ['ignore', log, log],
  });
  owned.push(child);
  return child;
}
async function ready(url, child) {
  for (let i = 0; i < 100; i++) {
    if (child.exitCode !== null) throw new Error(`Owned server exited: ${url}`);
    try {
      if ((await globalThis.fetch(url)).ok) return;
    } catch {
      /* Wait for owned startup. */
    }
    await new Promise((r) => globalThis.setTimeout(r, 100));
  }
  throw new Error(`Server did not start: ${url}`);
}
try {
  const demo = server(
    [
      'node_modules/vite/bin/vite.js',
      'preview',
      '--mode',
      'demo',
      '--host',
      '127.0.0.1',
      '--port',
      demoPort,
      '--strictPort',
    ],
    {},
    'demo-server.log',
  );
  const prod = server(
    ['scripts/projection-server.mjs'],
    { DASHBOARD_PORT: productionPort },
    'production-server.log',
  );
  await Promise.all([
    ready(`http://127.0.0.1:${demoPort}`, demo),
    ready(`http://127.0.0.1:${productionPort}`, prod),
  ]);
  const test = spawn(process.execPath, ['scripts/browser-w01.mjs'], {
    env: {
      ...process.env,
      DASHBOARD_PREVIEW_URL: `http://127.0.0.1:${demoPort}`,
      DASHBOARD_PRODUCTION_URL: `http://127.0.0.1:${productionPort}`,
    },
    stdio: 'inherit',
  });
  const result = await new Promise((resolve, reject) => {
    test.on('error', reject);
    test.on('exit', resolve);
  });
  if (result !== 0) throw new Error(`Browser checks exited ${result}`);
} finally {
  for (const child of owned) child.kill('SIGTERM');
}
