import fs from 'node:fs';
import { createHash } from 'node:crypto';
import { describe, expect, it } from 'vitest';
import yaml from 'yaml';
import Ajv from 'ajv';
import { responseSchemas } from '../src/api/schema';
import version from '../src/api/contract-version.json';
const raw = fs.readFileSync(
  '../docs/design/dashboard-api-v1-provisional.yaml',
  'utf8',
);
const contract = yaml.parse(raw);
const ajv = new Ajv({ allErrors: true, schemaId: 'auto' });
// This contract uses the common draft-07/2020-12 subset only. Ajv 6 validates
// those keywords; OpenAPI generation independently checks document structure.
ajv.addSchema(contract, 'contract');
describe('C0 provisional contract conformance', () => {
  it('matches the exact artifact version and SHA-256', () => {
    expect(contract.openapi).toBe('3.1.0');
    expect(contract.info.version).toBe(version.version);
    expect(createHash('sha256').update(raw).digest('hex')).toBe(version.sha256);
    expect(version.approval).toBe('PENDING');
  });
  it('exposes GET and HEAD only', () => {
    for (const path of Object.values(contract.paths))
      expect(Object.keys(path as object).sort()).toEqual(['get', 'head']);
  });
  for (let n = 0; n <= 11; n++)
    it(`F${n} conforms to both contract and runtime schemas`, () => {
      const world = JSON.parse(
        fs.readFileSync(`src/api/mock/fixtures/F${n}.json`, 'utf8'),
      );
      expect(world.contract_version).toBe(version.version);
      expect(world.contract_sha256).toBe(version.sha256);
      for (const [route, payload] of Object.entries(world.responses)) {
        const name = world.models[route] as keyof typeof responseSchemas;
        const validate = ajv.compile({
          $ref: `contract#/components/schemas/${name}`,
        });
        expect(validate(payload), JSON.stringify(validate.errors)).toBe(true);
        expect(responseSchemas[name].safeParse(payload).success, route).toBe(
          true,
        );
      }
      for (const payload of Object.values(world.pages)) {
        expect(
          ajv.validate(
            { $ref: 'contract#/components/schemas/WorkListResponse' },
            payload,
          ),
        ).toBe(true);
        expect(
          responseSchemas.WorkListResponse.safeParse(payload).success,
        ).toBe(true);
      }
    });
  it('rejects malformed envelopes and unbounded collections', () => {
    const world = JSON.parse(
      fs.readFileSync('src/api/mock/fixtures/F1.json', 'utf8'),
    );
    const work = world.responses['/work'];
    expect(
      responseSchemas.WorkListResponse.safeParse({
        ...work,
        schema_version: 'future',
      }).success,
    ).toBe(false);
    expect(
      responseSchemas.WorkListResponse.safeParse({
        ...work,
        generated_at: 'not a timestamp',
      }).success,
    ).toBe(false);
    expect(
      responseSchemas.WorkListResponse.safeParse({
        ...work,
        data: { items: Array(251).fill(work.data.items[0]), next_cursor: null },
      }).success,
    ).toBe(false);
  });
});
