import fs from 'node:fs';
import crypto from 'node:crypto';
import { z } from 'zod';
import { wireSchemas, investigationCases } from '../src/api/preview/investigation/schema.ts';
import { investigationFixture } from '../src/api/preview/investigation/fixtures.ts';
const write = process.argv.includes('--write');
const sha = text => crypto.createHash('sha256').update(text).digest('hex');
function artifact(file, value) {
  const text = JSON.stringify(value, null, 2) + '\n';
  if (write) fs.writeFileSync(file, text); else if (fs.readFileSync(file, 'utf8') !== text) throw new Error(`Investigation artifact drift: ${file}`);
  return sha(text);
}
const digest = artifact('docs/design/investigation-preview-0.1.0.json', {
  id: 'investigation-preview', version: '0.1.0', disposition: 'PROVISIONAL',
  routes: { base: '/api/preview/investigation/v0.1', methods: ['GET', 'HEAD'], sources: '/sources', source: '/sources/{source_id}', packet: '/packets/{packet_id}', items: '/packets/{packet_id}/items', parameters: ['case', 'work', 'source_id', 'section', 'disposition', 'cursor', 'limit=1..50'] },
  bounds: { section_summaries: 32, receipts: 100, page: 50, excerpt_bytes: 16384, page_excerpt_bytes: 131072 },
  rules: ['Packet, source and receipt bindings must match exact supplied identity and snapshot.', 'Raw prompt content, credentials and unauthorized candidate identities are excluded.', 'Source collection exposes summaries only; detail access is independent.', 'Fixed snapshots never advance silently.', 'Missing explanations and receipts are not inferred from adjacent content.', 'Structural comparison never establishes causation.', 'Canonical decisions remain references to their authoritative records. “Included in context” references do not establish delivery, use, or benefit.', 'Byte excerpt bounds supplement the JSON schemas at runtime.'],
  schemas: Object.fromEntries(Object.entries(wireSchemas).map(([key, schema]) => [key, z.toJSONSchema(schema)])),
});
artifact('docs/design/investigation-fixtures.manifest.json', { contract: 'investigation-preview', version: '0.1.0', sha256: digest, cases: Object.fromEntries(investigationCases.map(name => [name, { sha256: sha(JSON.stringify(investigationFixture(name))) }])) });
console.log('Investigation preview artifacts and fixtures match');
