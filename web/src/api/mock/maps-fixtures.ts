/** Explicitly fictional Maps projection; never imported by production readers. */
import seed from './fixtures/maps-history.json' with { type: 'json' };
import type { World } from './types';

export const fixtureMapRoots = ['a'.repeat(64), 'b'.repeat(64), ...Array.from({ length: 49 }, (_, index) => (index + 1).toString(16).padStart(64, '0'))];
const envelope = { schema_version: '0.1.3' as const, project_id: 'aew-demo', control_revision: '42', generated_at: '2026-10-10T00:00:00Z' };
const commit = 'c'.repeat(40);
const label = 'Derived navigation context; fictional fixture';
export function mapFixtureSummary(root: string) {
  return { root, status: 'AVAILABLE', reasons: [], selected: root === fixtureMapRoots[0], source_revision: root === fixtureMapRoots[1] ? 'd'.repeat(40) : commit, source_tree: 'e'.repeat(40), object_format: 'sha1', generator: { name: 'structural', version: 1, ruleset_sha256: 'f'.repeat(64) } };
}
export function installMapFixtures(world: World) {
  if (world.fixture !== 'F1') return world;
  const next = structuredClone(world);
  const caps = next.responses['/capabilities'] as { data: Record<string, unknown> };
  caps.data.maps = { state: 'AVAILABLE', reasons: [] };
  return next;
}
export class MapsFixtureProjector {
  read(path: string, params: URLSearchParams) {
    const against = params.get('against') ?? commit;
    const freshness = (root: string) => ({ status: root === fixtureMapRoots[1] ? 'STALE' : 'CURRENT', reasons: root === fixtureMapRoots[1] ? [{ code: 'MAP_STALE', message: 'Fictional metadata input changed.' }] : [], against_commit: against, against_tree: 'e'.repeat(40), metadata_paths: root === fixtureMapRoots[1] ? ['compile_commands.json'] : [], metadata_paths_omitted: 0 });
    if (path === '/maps') return { status: 200, body: ({ ...envelope, data: { map_revision: '0123456789abcdef:1', registry: { state: 'PRESENT', reasons: [] }, structural: { state: 'AVAILABLE', reasons: [], summary: mapFixtureSummary(fixtureMapRoots[0]), freshness: freshness(fixtureMapRoots[0]) }, architecture: { evidence: { kind: 'evidence', id: 'INV-0001-verification-1', title: 'Fictional architecture reference' }, freshness: { status: 'UNKNOWN', reasons: [], basis: null, observed_commit: null, authoritative_commit: against, scope: null, changed_paths: [], changed_paths_omitted: 0 }, note: 'Architecture references are not acceptance or an artifact path.' }, stored: { count: 60 }, label } }) };
    if (path === '/maps/diff') {
      const a = params.get('a')!, b = params.get('b')!;
      if (!fixtureMapRoots.includes(a) || !fixtureMapRoots.includes(b)) return { status: 404 };
      const data = structuredClone(seed.MapDiffResponse.data);
      data.a = { root: a, source_revision: mapFixtureSummary(a).source_revision, source_tree: 'e'.repeat(40) };
      data.b = { root: b, source_revision: mapFixtureSummary(b).source_revision, source_tree: 'e'.repeat(40) };
      data.identical = a === b;
      data.label = label;
      if (a !== b) { data.sections.directories.changed = true; data.sections.directories.beyond_cap = true; data.sections.directories.values = { rows_omitted: { from: 0, to: 2 } }; }
      return { status: 200, body: ({ ...envelope, data }) };
    }
    const match = /^\/maps\/structural\/([0-9a-f]{64})(\/inputs)?$/.exec(path);
    if (path !== '/maps/structural' && (!match || !fixtureMapRoots.includes(match[1]))) return { status: 404 };
    if (path === '/maps/structural' || match?.[2]) {
      const filter = params.get('source_revision') ?? '';
      const items = path === '/maps/structural' ? fixtureMapRoots.map(mapFixtureSummary).filter(item => !filter || item.source_revision === filter).sort((a, b) => a.root.localeCompare(b.root)) : Array.from({ length: 61 }, (_, index) => ({ path: index === 0 ? '<script>window.__mapsHostile=1</script>' : `src/fictional-${String(index).padStart(3, '0')}.ts`, git_oid: commit, size: 100, read: index < 50, reason: index < 50 ? 'read' : 'metadata_bytes_cap' }));
      const limit = Number(params.get('limit') ?? 50);
      let prior: { path: string; offset: number; filter: string } | undefined;
      if (params.has('cursor')) {
        try { prior = JSON.parse(atob(params.get('cursor')!.replace(/^maps-fixture-/, ''))); } catch { return { status: 400 }; }
      }
      if (!Number.isInteger(limit) || limit < 1 || limit > (match?.[2] ? 250 : 50) || (params.has('cursor') && (!prior || prior.path !== path || prior.filter !== filter || !Number.isInteger(prior.offset) || prior.offset < 0 || prior.offset > items.length))) return { status: 400 };
      const offset = prior?.offset ?? 0;
      const page = items.slice(offset, offset + limit);
      const next = offset + page.length < items.length ? `maps-fixture-${btoa(JSON.stringify({ path, filter, offset: offset + page.length }))}` : null;
      const body = { ...envelope, data: match?.[2] ? { root: match[1], items: page, next_cursor: next, cut_strings: 0, dropped_fields: 0, label } : { items: page, next_cursor: next, scan_incomplete: { examined: 51, stored: 60, reasons: [{ code: 'MAP_SCAN_INCOMPLETE', message: 'Fictional scan cap; absent entries remain unknown.' }] }, label } };
      return { status: 200, body: body };
    }
    const root = match![1];
    const detail = structuredClone(seed.StructuralDetailResponse.data);
    const sectionData = {
      directories: { rows: [{ path: 'src', depth: 1, files: 3, languages: ['typescript'], languages_omitted: 0, label: 'candidate' }], submodules: [], rows_total: 3, rows_omitted: 2, dropped_fields: 0, dropped_items: 0 },
      languages: { counts: { typescript: 3 }, counts_omitted: 0, unknown_files: 1, unknown_extensions: [], dropped_fields: 0, dropped_items: 0 },
      build_descriptors: { items: [{ path: 'package.json', kind: 'package_json', status: 'parsed' }], omitted: 0, dropped_fields: 0, dropped_items: 0 },
      entry_point_candidates: { items: [{ label: 'candidate', path: 'src/index.ts', rule: 'fixture_rule' }], dropped_fields: 0, dropped_items: 0 },
      test_candidates: { items: [{ kind: 'future_fixture_runner', path: 'tests/fictional.test.ts', source: 'fixture' }], dropped_fields: 0, dropped_items: 0 },
      generated_and_vendor: { items: [], omitted: 0, dropped_fields: 0, dropped_items: 0 },
      semantic_prerequisites: { items: [{ path: 'compile_commands.json', kind: 'compilation_database', source: 'fixture' }], dropped_fields: 0, dropped_items: 0 },
      limits_and_omissions: { caps_hit: [{ section: 'directories', field: 'rows', limit: 200, omitted: 2 }], parse_failures: [], unsupported: [], lfs_pointers: [], metadata_unread: 11, dropped_fields: 0, dropped_items: 0 },
    };
    const requested = params.get('section');
    if (requested && !Object.hasOwn(sectionData, requested)) return { status: 400 };
    const data = { ...detail, summary: mapFixtureSummary(root), freshness: freshness(root), inputs: { ...detail.inputs, count: 61, read: 50, capped_size: 0, capped_total: 11 }, sections: requested ? { [requested]: sectionData[requested as keyof typeof sectionData] } : sectionData, label };
    return { status: 200, body: ({ ...envelope, data }) };
  }
}
