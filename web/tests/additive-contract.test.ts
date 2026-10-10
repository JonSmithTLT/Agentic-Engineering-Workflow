import fs from 'node:fs';
import yaml from 'yaml';
import Ajv from 'ajv';
import { describe, expect, it } from 'vitest';
import { additiveResponseSchemas, MapText, MapLanguagesSection } from '../src/api/additive-schema';
import { responseSchemas } from '../src/api/schema';
import { historySearchRoute, mapDiffRoute, mapInputsRoute, structuralMapRoute, storedMapsRoute } from '../src/api/maps-history';
import { ReadTransport } from '../src/api/transport';
const fixtures = JSON.parse(fs.readFileSync('src/api/mock/fixtures/maps-history.json','utf8'));
const contract = yaml.parse(fs.readFileSync('../docs/design/dashboard-api-v1-provisional.yaml','utf8'));
const ajv = new Ajv({ allErrors: true });
ajv.addSchema(contract, 'contract');
describe('Additive contract readiness', () => {
  for (const [name, schema] of Object.entries(additiveResponseSchemas)) {
    it(`${name} accepts bounded fixture through wire and runtime validators`, () => {
      const payload = fixtures[name];
      const validate = ajv.compile({ $ref: `contract#/components/schemas/${name}` });
      expect(validate(payload), JSON.stringify(validate.errors)).toBe(true);
      expect(schema.safeParse(payload).success).toBe(true);
      expect(schema.safeParse({ ...payload, schema_version: '0.1.2' }).success).toBe(false);
      expect(schema.safeParse({ ...payload, unexpected: true }).success).toBe(false);
    });
  }
  it('old routes still reject new envelope versions', () => {
    const fixture = JSON.parse(fs.readFileSync('src/api/mock/fixtures/F1.json','utf8'));
    for (const [route,payload] of Object.entries(fixture.responses)) {
      const schema = responseSchemas[fixture.models[route] as keyof typeof responseSchemas];
      expect(schema.safeParse(payload).success, route).toBe(true);
      expect(schema.safeParse({ ...(payload as object), schema_version:'0.1.3' }).success,route).toBe(false);
    }
  });
  it('rejects oversized result collections and unsafe integers', () => {
    const list = fixtures.StructuralListResponse;
    const summary=fixtures.StructuralDetailResponse.data.summary;
    expect(additiveResponseSchemas.StructuralListResponse.safeParse({ ...list,data:{...list.data,items:Array(51).fill(summary)}}).success).toBe(false);
    const inputs=fixtures.StructuralInputsResponse;
    expect(additiveResponseSchemas.StructuralInputsResponse.safeParse({...inputs,data:{...inputs.data,items:Array(251).fill({path:'fixture',read:false})}}).success).toBe(false);
    const search=fixtures.HistorySearchResponse;
    expect(additiveResponseSchemas.HistorySearchResponse.safeParse({...search,data:{...search.data,coverage:{...search.data.coverage,history_entries:9007199254740992}}}).success).toBe(false);
  });
  it('keeps open semantic values while rejecting undeclared paths and commands', () => {
    const fixture=fixtures.StructuralDetailResponse;
    expect(additiveResponseSchemas.StructuralDetailResponse.safeParse({...fixture,data:{...fixture.data,summary:{...fixture.data.summary,status:'FUTURE_STATUS'}}}).success).toBe(true);
    expect(additiveResponseSchemas.StructuralDetailResponse.safeParse({...fixture,data:{...fixture.data,storage_path:'/private'}}).success).toBe(false);
  });
  it('counts code points and bounds dictionary keys/properties', () => {
    expect(MapText.safeParse('😀'.repeat(520)).success).toBe(true);
    expect(MapText.safeParse('😀'.repeat(521)).success).toBe(false);
    const section = {counts:{['x'.repeat(33)]:0},counts_omitted:0,unknown_files:0,unknown_extensions:[],unknown_extensions_omitted:0,dropped_fields:0,dropped_items:0};
    expect(MapLanguagesSection.safeParse({...section, counts:{typescript:0}}).success).toBe(true);
    expect(MapLanguagesSection.safeParse(section).success).toBe(false);
  });
  it('keeps old/new route validators independent and preserves both 304 payloads', async () => {
    const old = JSON.parse(fs.readFileSync('src/api/mock/fixtures/F1.json','utf8')).responses['/overview'];
    const seen = new Map<string, number>();
    const client = new ReadTransport(async input => {
      const route = String(input);
      const count = seen.get(route) ?? 0;
      seen.set(route,count+1);
      return count ? new Response(null,{status:304}) : new Response(JSON.stringify(route.endsWith('/maps') ? fixtures.MapsResponse : old),{headers:{'Content-Type':'application/json',ETag:'"same"'}});
    });
    const maps = await client.get('/maps',additiveResponseSchemas.MapsResponse);
    const overview = await client.get('/overview',responseSchemas.OverviewResponse);
    expect((await client.get('/maps',additiveResponseSchemas.MapsResponse)).value).toBe(maps.value);
    expect((await client.get('/overview',responseSchemas.OverviewResponse)).value).toBe(overview.value);
    expect(maps.value.schema_version).toBe('0.1.3');
    expect(overview.value.schema_version).toBe('0.1.2');
  });
});
describe('Exact, bounded request identities', () => {
  const root='a'.repeat(64);
  it('accepts opaque cursor while refusing refs/paths/short roots and oversized pages', () => {
    expect(mapInputsRoute(root,{cursor:'opaque:+/=',limit:250})).toContain('cursor=opaque%3A%2B%2F%3D');
    for(const invalid of ['HEAD','--all','../file','a'.repeat(40)]) expect(()=>structuralMapRoute(invalid)).toThrow();
    expect(()=>storedMapsRoute({source_revision:'HEAD'})).toThrow();
    expect(()=>mapInputsRoute(root,{limit:251})).toThrow();
    expect(()=>mapDiffRoute(root,'HEAD')).toThrow();
  });
  it('preserves every repeated literal term and kind without a fetch', () => {
    const params = new URLSearchParams(historySearchRoute({terms:['clangd','a & b'],kinds:['evidence','ticket']}).split('?')[1]);
    expect(params.getAll('term')).toEqual(['clangd','a & b']);
    expect(params.getAll('kind')).toEqual(['evidence','ticket']);
    expect(params.get('limit')).toBe('10');
  });
  it('rejects empty/oversized/encoded-over-budget or reversed-date queries', () => {
    expect(()=>historySearchRoute({terms:[]})).toThrow();
    expect(()=>historySearchRoute({terms:['x'.repeat(513)]})).toThrow();
    expect(()=>historySearchRoute({terms:['😀'.repeat(512)]})).toThrow();
    expect(()=>historySearchRoute({terms:['fixture'],since:'2026-10-10T01:00:00Z',until:'2026-10-10T00:00:00Z'})).toThrow();
    expect(()=>historySearchRoute({terms:['fixture'],since:'2026-10-10T00:00:00Z',until:'2026-10-10T00:00:00.9Z'})).not.toThrow();
  });
});
