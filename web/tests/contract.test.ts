import fs from 'node:fs';
import { createHash } from 'node:crypto';
import { describe, expect, it } from 'vitest';
import yaml from 'yaml';
import Ajv from 'ajv';
import {
  id,
  cursor,
  work,
  invocation,
  evidenceBindings,
  historyDetail,
  integrity,
  responseSchemas,
} from '../src/api/schema';
import version from '../src/api/contract-version.json';
import approval from '../docs/c0-approval.json';
import * as vocabulary from '../src/api/vocabulary';
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
    expect(createHash('sha256').update(raw).digest('hex')).toBe(
      version.sha256,
    );
    expect(version.approval).toBe('PENDING');
    expect(approval.status).toBe('PENDING');
    expect(approval.contract_version).toBe(version.version);
    expect(approval.sha256).toBe(version.sha256);
    expect(approval.previous_reviews[0].disposition).toBe('AMEND');
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
        expect(validate(payload), JSON.stringify(validate.errors)).toBe(
          true,
        );
        expect(
          responseSchemas[name].safeParse(payload).success,
          route,
        ).toBe(true);
      }
      for (const [route, payload] of Object.entries(
        world.provisional_responses,
      )) {
        const model = world.provisional_models[
          route
        ] as keyof typeof responseSchemas;
        expect(
          ajv.validate(
            { $ref: `contract#/components/schemas/${model}` },
            payload,
          ),
          JSON.stringify(ajv.errors),
        ).toBe(true);
        expect(responseSchemas[model].safeParse(payload).success).toBe(
          true,
        );
        expect(world.responses['/capabilities'].data.integrity.state).toBe(
          'UNSUPPORTED',
        );
        expect(world.responses[route]).toBeUndefined();
      }
      for (const [token, payload] of Object.entries(world.pages)) {
        const model = world.page_models[
          token
        ] as keyof typeof responseSchemas;
        expect(
          ajv.validate(
            { $ref: `contract#/components/schemas/${model}` },
            payload,
          ),
        ).toBe(true);
        expect(responseSchemas[model].safeParse(payload).success).toBe(
          true,
        );
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
        data: {
          items: Array(251).fill(work.data.items[0]),
          next_cursor: null,
        },
      }).success,
    ).toBe(false);
  });
});

const normal = JSON.parse(
  fs.readFileSync('src/api/mock/fixtures/F1.json', 'utf8'),
);
it('rejects old work fields, out-of-range risk and execution paths in bindings', () => {
  const ticket = normal.responses['/work/T-0001'].data;
  expect(
    work.safeParse({ ...ticket, classification: 'CLASS_0' }).success,
  ).toBe(false);
  expect(work.safeParse({ ...ticket, risk_class: 5 }).success).toBe(false);
  expect(work.safeParse({ ...ticket, risk_class: 2.5 }).success).toBe(
    false,
  );
  expect(work.safeParse({ ...ticket, plan_revision: 0 }).success).toBe(
    false,
  );
  expect(
    work.safeParse({
      ...ticket,
      state: 'FUTURE_WORK_STATE',
      reasons: [
        { code: 'future free text', message: 'Backend explanation' },
      ],
    }).success,
  ).toBe(true);
  const bindings = normal.responses['/evidence'].data.items[0].bindings;
  expect(
    evidenceBindings.safeParse({ ...bindings, workspace_id: '/tmp/work' })
      .success,
  ).toBe(false);
  expect(
    evidenceBindings.safeParse({
      ...bindings,
      producer: { ...bindings.producer, run_dir: '/tmp/run' },
    }).success,
  ).toBe(false);
  expect(
    evidenceBindings.safeParse({
      ...bindings,
      evaluated_snapshot: {
        ...bindings.evaluated_snapshot,
        workspace_id: '/tmp/ws',
      },
    }).success,
  ).toBe(false);
});
it('preserves path-safe opaque IDs and distinct unrestricted opaque cursors', () => {
  for (const value of ['T-0001', 'INV-0001-review-1', 'project.slug_1'])
    expect(id.safeParse(value).success).toBe(true);
  for (const value of ['.', '..', '/tmp/record', 'work:1', 'space id'])
    expect(id.safeParse(value).success).toBe(false);
  expect(cursor.safeParse('opaque:+/=snapshot').success).toBe(true);
  expect(
    responseSchemas.WorkResponse.safeParse({
      ...normal.responses['/work/T-0001'],
      control_revision: 'r42',
    }).success,
  ).toBe(false);
});
it('models invocations including manual invocations without harness runs', () => {
  const manual = normal.responses['/runs/INV-0002'].data;
  expect(invocation.safeParse(manual).success).toBe(true);
  expect(manual.runs).toEqual([]);
  expect(
    invocation.safeParse({ ...manual, run_dir: '/tmp/run' }).success,
  ).toBe(false);
  expect(contract.paths['/queue']).toBeUndefined();
  expect(contract.components.schemas.Queue).toBeUndefined();
  expect(normal.responses['/capabilities'].data.queue.state).toBe(
    'UNSUPPORTED',
  );
});
it('requires manifest trust labels, list annotations and structured integrity roots', () => {
  const record = normal.responses['/history/T-0004'].data;
  expect(record.annotations.map((x: { rel: string }) => x.rel)).toEqual([
    'moved_to',
    'lineage',
  ]);
  expect(record.parent).toBe('S-0001');
  for (const forbidden of ['path', 'currentness', 'lineage'])
    expect(
      historyDetail.safeParse({ ...record, [forbidden]: 'bad' }).success,
    ).toBe(false);
  expect(
    historyDetail.safeParse({ ...record, source: undefined }).success,
  ).toBe(false);
  expect(
    historyDetail.safeParse({ ...record, annotations: 'moved' }).success,
  ).toBe(false);
  const future = JSON.parse(
    fs.readFileSync('src/api/mock/fixtures/F4.json', 'utf8'),
  ).provisional_responses['/history/integrity'].data;
  expect(
    integrity.safeParse({ ...future, current_root: 'root-42' }).success,
  ).toBe(false);
  expect(
    integrity.safeParse({ ...future, verified: 'root-40' }).success,
  ).toBe(false);
});
it('documents per-route statuses and declares backend filters', () => {
  for (const [route, ops] of Object.entries(contract.paths)) {
    const operation = (
      ops as { get: { responses: Record<string, unknown> } }
    ).get;
    expect('404' in operation.responses).toBe(route.includes('{id}'));
    expect('409' in operation.responses).toBe(
      [
        '/work',
        '/runs',
        '/evidence',
        '/knowledge',
        '/attention',
        '/activity',
      ].includes(route),
    );
  }
  for (const [route, filters] of Object.entries({
    '/work': ['state', 'kind', 'parent'],
    '/history': ['kind', 'since', 'until'],
    '/evidence': ['work'],
  })) {
    expect(
      contract.paths[route].get.parameters.map(
        (p: { name: string }) => p.name,
      ),
    ).toEqual(expect.arrayContaining(filters));
  }
});
it('keeps known vocabularies aligned while wire semantic strings remain open', () => {
  const pairs = {
    TicketState: vocabulary.ticketStates,
    ParentState: vocabulary.parentStates,
    InvocationRole: vocabulary.invocationRoles,
    InvocationStatus: vocabulary.invocationStatuses,
    HarnessStatus: vocabulary.harnessStatuses,
    DecisionType: vocabulary.decisionTypes,
  };
  for (const [name, values] of Object.entries(pairs))
    expect(contract.components.schemas[name]['x-known-values']).toEqual([
      ...values,
    ]);
  const schemas = contract.components.schemas;
  const inline = [
    [schemas.Evidence.properties.kind, vocabulary.evidenceKinds],
    [
      schemas.Evidence.properties.result.anyOf[0],
      vocabulary.evidenceResults,
    ],
    [
      schemas.Evidence.properties.currentness,
      vocabulary.evidenceCurrentness,
    ],
    [schemas.History.properties.kind, vocabulary.historyKinds],
    [schemas.History.properties.source, vocabulary.trustSources],
    [schemas.Annotation.properties.rel, vocabulary.annotationRelations],
  ];
  for (const [shape, values] of inline)
    expect(shape['x-known-values']).toEqual([...values]);
});
