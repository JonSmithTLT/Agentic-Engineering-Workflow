import { ObjectId, Sha256 } from './additive-schema';
import { historicalRequested } from './navigation';
export const mapSections = ['directories', 'languages', 'build_descriptors', 'entry_point_candidates', 'test_candidates', 'generated_and_vendor', 'semantic_prerequisites', 'limits_and_omissions'] as const;
export const mapActivities = ['selected', 'stored', 'compare'] as const;
export const mapTabs = ['sections', 'inputs', 'provenance'] as const;
export const mapPresentationKeys = ['map_activity', 'map_root', 'map_against', 'map_tab', 'map_section', 'map_cursor', 'map_input_cursor', 'map_source_revision', 'map_a', 'map_b'] as const;
export function mapPresentation(params: URLSearchParams) {
  if (historicalRequested(params)) throw new Error('Historical snapshot reads are not supported by Maps.');
  for (const key of params.keys()) if (key.startsWith('map_') && !(mapPresentationKeys as readonly string[]).includes(key)) throw new Error('Unsupported Maps presentation parameter.');
  for (const key of mapPresentationKeys) {
    if (params.getAll(key).length > 1) throw new Error('Repeated Maps presentation parameters are unsupported.');
  }
  const activity = params.get('map_activity') ?? 'selected';
  const tab = params.get('map_tab') ?? 'sections';
  const section = params.get('map_section') ?? 'directories';
  if (!(mapActivities as readonly string[]).includes(activity) || !(mapTabs as readonly string[]).includes(tab) || !(mapSections as readonly string[]).includes(section)) throw new Error('Unsupported Maps presentation value.');
  for (const key of ['map_root', 'map_a', 'map_b']) if (params.has(key) && !Sha256.safeParse(params.get(key)).success) throw new Error('Maps roots must be complete SHA-256 identities.');
  for (const key of ['map_against', 'map_source_revision']) if (params.has(key) && !ObjectId.safeParse(params.get(key)).success) throw new Error('Maps commits must be complete object identities.');
  for (const key of ['map_cursor', 'map_input_cursor']) if (params.has(key) && !params.get(key)) throw new Error('Empty Maps cursors are unsupported.');
  return { activity, tab, section: section as typeof mapSections[number], root: params.get('map_root'), against: params.get('map_against') ?? undefined, a: params.get('map_a'), b: params.get('map_b') };
}
