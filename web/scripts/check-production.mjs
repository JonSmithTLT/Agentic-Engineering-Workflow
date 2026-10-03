import fs from 'node:fs';
import path from 'node:path';
function files(dir) {
  return fs
    .readdirSync(dir, { withFileTypes: true })
    .flatMap((entry) =>
      entry.isDirectory()
        ? files(path.join(dir, entry.name))
        : [path.join(dir, entry.name)],
    );
}
for (const file of files('dist')) {
  const text = fs.readFileSync(file, 'utf8');
  if (
    /W01_REPLAY_CATALOG|Manual replay|Contract Playground|scenario-config|mockServiceWorker|setupWorker|Demo data|project:demo\/aew|aew-demo|FUTURE_WORK_STATE|attacker\.invalid|Mock Service Worker/.test(
      text,
    )
  )
    throw new Error(`Production mock leakage: ${file}`);
}
console.log('Production build excludes fixtures and mock initialization');
