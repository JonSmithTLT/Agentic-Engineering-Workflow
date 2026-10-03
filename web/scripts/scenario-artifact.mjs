import fs from 'node:fs';
import { createHash } from 'node:crypto';
import { generatedScenarioSchema } from '../src/api/mock/lab/config.ts';
const schema = JSON.stringify(generatedScenarioSchema(), null, 2) + '\n';
const manifest =
  JSON.stringify(
    {
      kind: 'developer-harness-configuration',
      version: '1.0.0',
      artifact: 'scenario-config.schema.json',
      sha256: createHash('sha256').update(schema).digest('hex'),
    },
    null,
    2,
  ) + '\n';
for (const [name, text] of [
  ['scenario-config.schema.json', schema],
  ['scenario-config.manifest.json', manifest],
]) {
  const file = `docs/design/${name}`;
  if (process.argv.includes('--write')) fs.writeFileSync(file, text);
  else if (fs.readFileSync(file, 'utf8') !== text)
    throw new Error(`Scenario artifact drift: ${file}`);
}
console.log('Scenario configuration artifacts match their runtime schema');
