import { expect, it } from 'vitest';
import { mapPresentation } from '../src/api/maps-presentation';
import { dashboardCopyLink } from '../src/api/navigation';
import { MapsFixtureProjector, fixtureMapRoots } from '../src/api/mock/maps-fixtures';
import { additiveResponseSchemas } from '../src/api/additive-schema';

it('requires full explicit identities and refuses unsupported or repeated presentation before reads', () => {
  for (const value of ['map_root=HEAD', 'map_against=main', 'map_scope=all', 'map_activity=replay', 'map_tab=graph', 'map_root=' + 'a'.repeat(40), 'map_section=commands', 'map_tab=inputs&map_tab=provenance']) expect(() => mapPresentation(new URLSearchParams(value))).toThrow();
  expect(mapPresentation(new URLSearchParams(`map_root=${fixtureMapRoots[0]}&map_against=${'c'.repeat(40)}`)).root).toBe(fixtureMapRoots[0]);
});
it('copies Maps identity and presentation but never arbitrary paths or terms', () => {
  const link = new URL(dashboardCopyLink('/maps', `?map_root=${fixtureMapRoots[0]}&map_tab=inputs&map_input_cursor=opaque&path=/private&term=private`, 'https://example.invalid'));
  expect(link.searchParams.get('map_root')).toBe(fixtureMapRoots[0]);
  expect(link.searchParams.get('map_input_cursor')).toBe('opaque');
  expect(link.searchParams.has('path')).toBe(false);
  expect(link.searchParams.has('term')).toBe(false);
});
it('validates all fictional Maps projections under the unchanged accepted parsers', () => {
  const projector = new MapsFixtureProjector();
  const cases = [
    ['/maps', '', additiveResponseSchemas.MapsResponse],
    ['/maps/structural', 'limit=50', additiveResponseSchemas.StructuralListResponse],
    [`/maps/structural/${fixtureMapRoots[0]}`, 'section=directories', additiveResponseSchemas.StructuralDetailResponse],
    [`/maps/structural/${fixtureMapRoots[0]}/inputs`, 'limit=50', additiveResponseSchemas.StructuralInputsResponse],
    ['/maps/diff', `a=${fixtureMapRoots[0]}&b=${fixtureMapRoots[1]}`, additiveResponseSchemas.MapDiffResponse],
  ] as const;
  for (const [path, params, schema] of cases) expect(schema.safeParse(projector.read(path, new URLSearchParams(params)).body).success).toBe(true);
});
it('replaces input pages and binds opaque cursors to their exact owning root', () => {
  const projector = new MapsFixtureProjector();
  const path = `/maps/structural/${fixtureMapRoots[0]}/inputs`;
  const first = additiveResponseSchemas.StructuralInputsResponse.parse(projector.read(path, new URLSearchParams('limit=50')).body);
  expect(first.data.items).toHaveLength(50);
  const params = new URLSearchParams({ limit: '50', cursor: first.data.next_cursor! });
  const second = additiveResponseSchemas.StructuralInputsResponse.parse(projector.read(path, params).body);
  expect(second.data.items).toHaveLength(11);
  expect(second.data.next_cursor).toBeNull();
  expect(projector.read(`/maps/structural/${fixtureMapRoots[1]}/inputs`, params).status).toBe(400);
});
it('preserves explicit differences beyond a supplied cap and rejects missing operands', () => {
  const projector = new MapsFixtureProjector();
  const response = additiveResponseSchemas.MapDiffResponse.parse(projector.read('/maps/diff', new URLSearchParams({ a: fixtureMapRoots[0], b: fixtureMapRoots[1] })).body);
  expect(response.data.sections.directories.beyond_cap).toBe(true);
  expect(response.data.identical).toBe(false);
  expect(projector.read('/maps/diff', new URLSearchParams({ a: fixtureMapRoots[0], b: 'f'.repeat(64) })).status).toBe(404);
});
