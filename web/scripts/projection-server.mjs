/** Test-only same-origin fixture adapter. Never included in the production build. */
import http from 'node:http';
import { Buffer } from 'node:buffer';
import { URL } from 'node:url';
import fs from 'node:fs';
import path from 'node:path';
import ts from 'typescript';
import { createHash } from 'node:crypto';
const source = fs.readFileSync('src/api/mock/projector.ts', 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.ES2022,
  },
}).outputText;
const { DemoProjector } = await import(
  'data:text/javascript;base64,' + Buffer.from(compiled).toString('base64')
);
const world = JSON.parse(
  fs.readFileSync('src/api/mock/fixtures/F1.json', 'utf8'),
);
const projector = new DemoProjector(world);
const root = path.resolve(process.env.DASHBOARD_STATIC_ROOT ?? 'dist');
const csp =
  "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'";
const server = http.createServer((req, res) => {
  res.setHeader('Content-Security-Policy', csp);
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Referrer-Policy', 'no-referrer');
  if (!['GET', 'HEAD'].includes(req.method)) {
    res.writeHead(405);
    res.end();
    return;
  }
  const url = new URL(req.url, 'http://127.0.0.1');
  if (url.pathname.startsWith('/api/v1/')) {
    const result = projector.read(url);
    const text = JSON.stringify(
      result.body ?? { message: 'Test projection missing' },
    );
    const etag =
      '"' +
      createHash('sha256')
        .update(url.pathname + url.search + text)
        .digest('hex') +
      '"';
    res.setHeader('Content-Type', 'application/json');
    res.setHeader('ETag', etag);
    if (result.status === 200 && req.headers['if-none-match'] === etag) {
      res.writeHead(304);
      res.end();
      return;
    }
    res.writeHead(result.status);
    res.end(req.method === 'HEAD' ? undefined : text);
    return;
  }
  if (url.pathname === '/favicon.ico') {
    res.writeHead(204);
    res.end();
    return;
  }
  const decoded = decodeURIComponent(url.pathname);
  let file = path.resolve(root, '.' + decoded);
  if (!file.startsWith(root + path.sep) && file !== root) {
    res.writeHead(400);
    res.end();
    return;
  }
  if (!path.extname(file) || file === root)
    file = path.join(root, 'index.html');
  if (!fs.existsSync(file)) {
    res.writeHead(404);
    res.end();
    return;
  }
  const types = {
    '.html': 'text/html',
    '.js': 'application/javascript',
    '.css': 'text/css',
  };
  res.setHeader(
    'Content-Type',
    types[path.extname(file)] ?? 'application/octet-stream',
  );
  res.writeHead(200);
  res.end(req.method === 'HEAD' ? undefined : fs.readFileSync(file));
});
const port = Number(process.env.DASHBOARD_PORT ?? 4175);
server.listen(port, '127.0.0.1', () =>
  console.log(`Test fixture adapter: http://127.0.0.1:${port}`),
);
