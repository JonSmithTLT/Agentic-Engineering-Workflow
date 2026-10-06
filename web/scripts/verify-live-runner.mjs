/** Test-only authenticated fixture adapter for runner regression. NOT F20.6 live acceptance. */
import http from 'node:http';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { Buffer } from 'node:buffer';
import { spawn } from 'node:child_process';
import assert from 'node:assert/strict';
import ts from 'typescript';

const compiled = ts.transpileModule(fs.readFileSync('src/api/mock/projector.ts', 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
}).outputText;
const { DemoProjector } = await import('data:text/javascript;base64,' + Buffer.from(compiled).toString('base64'));
const world = JSON.parse(fs.readFileSync('src/api/mock/fixtures/F1.json', 'utf8'));
world.responses['/capabilities'].data.action_projection = { state: 'UNSUPPORTED', reasons: [] };
world.responses['/capabilities'].data.queue = { state: 'UNSUPPORTED', reasons: [] };
const projector = new DemoProjector(world);
const secret = 'aew1.runner.privateTestSecret';
let fault = '', apiRequests = 0;
const root = path.resolve(process.env.DASHBOARD_STATIC_ROOT ?? 'dist');
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'aew-live-regression-'));
const file = path.join(dir, 'session.json');
const output = path.join(dir, 'report.json');
const server = http.createServer((req, res) => {
  const url = new globalThis.URL(req.url, 'http://127.0.0.1');
  res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'");
  res.setHeader('X-Content-Type-Options', 'nosniff');
  if (url.pathname.startsWith('/api/v1/')) {
    apiRequests++;
    res.setHeader('Content-Type', 'application/json');
    if (fault !== 'auth-bypass' && req.headers.cookie !== `aew_session=${secret}`) {
      res.writeHead(401); res.end(JSON.stringify({ code: 'SESSION_REQUIRED', message: 'Session required', reasons: [] })); return;
    }
    const result = projector.read(url);
    if (fault === 'malformed' && url.pathname === '/api/v1/capabilities') result.body.extra = secret;
    res.writeHead(result.status);
    res.end(JSON.stringify(result.body)); return;
  }
  if (url.pathname === '/favicon.ico') { res.writeHead(204); res.end(); return; }
  let target = path.resolve(root, '.' + url.pathname);
  if (!target.startsWith(root + path.sep) && target !== root) { res.writeHead(404); res.end(); return; }
  if (!path.extname(target)) target = path.join(root, 'index.html');
  if (!fs.existsSync(target)) { res.writeHead(404); res.end(); return; }
  res.setHeader('Content-Type', { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css' }[path.extname(target)] ?? 'application/octet-stream');
  res.end(fs.readFileSync(target));
});
try {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  fs.writeFileSync(file, JSON.stringify({ version: 1, origin, cookie: { name: 'aew_session', value: secret } }), { mode: 0o600 });
  async function run(expected, mode) {
    fault = mode;
    const child = spawn(process.execPath, ['--experimental-strip-types', 'scripts/browser-live.mjs'], {
      env: { ...process.env, DASHBOARD_BASE_URL: origin, DASHBOARD_SESSION_FILE: file, DASHBOARD_LIVE_OUTPUT: output },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let logs = '';
    child.stdout.on('data', chunk => { logs += chunk; });
    child.stderr.on('data', chunk => { logs += chunk; });
    const exit = await new Promise((resolve, reject) => { child.on('error', reject); child.on('exit', resolve); });
    const report = fs.readFileSync(output, 'utf8');
    assert(!logs.includes(secret) && !report.includes(secret), 'Credential escaped sanitized boundary');
    assert.equal(exit, expected, logs + report);
    const result = JSON.parse(report);
    assert.equal(result.status, expected === 0 ? 'PASS' : 'FAIL');
    if (mode === 'auth-bypass') assert.equal(result.failed_stage, 'unauthenticated-api-refusal');
    else if (mode === 'malformed') assert.equal(result.failed_stage, 'desktop-authenticated-bootstrap');
    else {
      assert(result.checks.includes('phone: missing session shows refusal and no Work table'));
      assert(result.checks.includes('desktop: Work copied selection reloads against the same authenticated origin'));
      assert.equal(result.counts.blocked_requests, 0);
      assert.equal(result.counts.invalid_responses, 0);
    }
    console.log(`PASS live-runner regression: ${mode || 'authenticated desktop/phone'}, test adapter only`);
  }
  await run(0, '');
  assert(apiRequests > 0);
  await run(1, 'auth-bypass');
  await run(1, 'malformed');
} finally {
  server.closeAllConnections();
  await new Promise(resolve => server.close(resolve));
  fs.rmSync(dir, { recursive: true, force: true });
}
