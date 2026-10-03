/** Local demo-only HTTP adapter. No service worker or backend implementation. */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { Buffer } from 'node:buffer';
import ts from 'typescript';
import { URL, pathToFileURL } from 'node:url';
async function loadProjector(file) {
  const location = pathToFileURL(path.resolve(file));
  const compiled = ts.transpileModule(fs.readFileSync(file, 'utf8'), {compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022}}).outputText
    .replace(/from (['"])(\.[^'"]+)\1/g, (_match, quote, reference) => `from ${quote}${new URL(reference + '.ts', location).href}${quote}`);
  return import('data:text/javascript;base64,' + Buffer.from(compiled).toString('base64'));
}
const { DemoProjector } = await loadProjector('src/api/mock/projector.ts');
const { JournalProjector, previewBase } = await loadProjector('src/api/preview/journal/projector.ts');
const { InvestigationProjector, investigationBase } = await loadProjector('src/api/preview/investigation/projector.ts');
const root = path.resolve(process.env.DASHBOARD_STATIC_ROOT ?? 'dist-demo');
const worlds = new Map(fs.readdirSync('src/api/mock/fixtures').filter((n) => /^F\d+\.json$/.test(n)).map((n) => {
  const world = JSON.parse(fs.readFileSync('src/api/mock/fixtures/' + n, 'utf8'));
  return [world.fixture, world];
}));
const accepted = new Map(), journals = new Map(), investigations = new Map(), checks = new Map();
const csp = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'";
const server = http.createServer((req, res) => {
  res.setHeader('Content-Security-Policy', csp);
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Referrer-Policy', 'no-referrer');
  if (!['GET', 'HEAD'].includes(req.method)) { res.writeHead(405); res.end(); return; }
  try {
    const url = new URL(req.url, 'http://127.0.0.1');
    if (url.pathname.startsWith('/api/')) {
      const fixture = req.headers['x-aew-demo-fixture'] ?? 'F1', world = worlds.get(fixture);
      if (!world) { res.writeHead(400); res.end(); return; }
      const investigation = url.pathname.startsWith(investigationBase + '/');
      const preview = investigation || url.pathname.startsWith(previewBase + '/');
      const store = investigation ? investigations : preview ? journals : accepted;
      if (!store.has(fixture)) store.set(fixture, investigation ? new InvestigationProjector(fixture, world.responses['/runs']?.data?.items ?? []) : preview ? new JournalProjector() : new DemoProjector(world));
      const countKey = JSON.stringify([fixture, req.headers['x-aew-demo-fault'], url.pathname, url.search]);
      const count = (checks.get(countKey) ?? 0) + 1; checks.set(countKey, count);
      let result;
      if (preview && url.searchParams.get('case') === 'refresh-error' && count > 1) result = {status: 500};
      else if (!preview && fixture === 'F10') {
        const fault = req.headers['x-aew-demo-fault'];
        if (fault === 'offline') { req.socket.destroy(); return; }
        result = fault === 'malformed' ? {status: 200, body: {bad: 'projection'}} : {status: fault === '404' ? 404 : 500};
      } else if (!preview && fixture === 'F11' && req.headers['x-aew-demo-fault'] === 'refresh-error' && count > 1) result = {status: 500};
      else if (preview) {
        const project = world.responses['/project'];
        result = store.get(fixture).read(url, project.project_id, project.control_revision);
      } else if (url.pathname.startsWith('/api/v1/')) result = store.get(fixture).read(url);
      else result = {status: 404};
      const text = JSON.stringify(result.body ?? {message: 'Demo projection unavailable'});
      res.setHeader('Content-Type', 'application/json');
      res.setHeader('Cache-Control', 'no-cache');
      if (result.status === 200) {
        const tag = '"' + createHash('sha256').update(url.pathname + url.search + text).digest('hex') + '"';
        res.setHeader('ETag', tag);
        if (req.headers['if-none-match'] === tag) { res.writeHead(304); res.end(); return; }
      }
      res.writeHead(result.status); res.end(req.method === 'HEAD' ? undefined : text); return;
    }
    if (url.pathname === '/favicon.ico') { res.writeHead(204); res.end(); return; }
    if (url.pathname === '/mockServiceWorker.js') { res.writeHead(404); res.end(); return; }
    let file = path.resolve(root, '.' + decodeURIComponent(url.pathname));
    if (!file.startsWith(root + path.sep) && file !== root) { res.writeHead(400); res.end(); return; }
    if (!path.extname(file) || file === root) file = path.join(root, 'index.html');
    if (!fs.existsSync(file) || !fs.statSync(file).isFile()) { res.writeHead(404); res.end(); return; }
    const types = {'.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png'};
    res.setHeader('Content-Type', types[path.extname(file)] ?? 'application/octet-stream');
    res.setHeader('Cache-Control', 'no-store');
    let content = fs.readFileSync(file);
    if (file === path.join(root, 'index.html')) content = content.toString().replace('<head>', '<head><meta name="aew-demo-transport" content="http">');
    res.writeHead(200); res.end(req.method === 'HEAD' ? undefined : content);
  } catch { if (!res.headersSent) res.writeHead(400); res.end(); }
});
const port = Number(process.env.DASHBOARD_PORT ?? 4249);
server.listen(port, '127.0.0.1', () => console.log(`Demo HTTP fixtures (no service worker): http://127.0.0.1:${port}`));
