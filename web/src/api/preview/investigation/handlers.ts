import { http, HttpResponse } from 'msw';
import { selectedWorld } from '../../mock/worlds';
import { representationTag } from '../../mock/projector';
import { InvestigationProjector, investigationBase } from './projector';
const projectors = new Map<string, InvestigationProjector>();
async function respond({ request }: { request: Request }) {
  const world = selectedWorld(), url = new URL(request.url);
  let projector = projectors.get(world.fixture); if (!projector) { const list = world.responses['/runs'] as { data?: { items?: unknown[] } }; projector = new InvestigationProjector(world.fixture, list?.data?.items ?? []); projectors.set(world.fixture, projector); }
  const project = world.responses['/project'] as { project_id: string; control_revision: string };
  const result = projector.read(url, project.project_id, project.control_revision);
  if (result.status !== 200) return new HttpResponse(null, { status: result.status });
  const tag = await representationTag(url, result.body);
  if (request.headers.get('If-None-Match') === tag) return new HttpResponse(null, { status: 304, headers: { ETag: tag } });
  return new HttpResponse(request.method === 'HEAD' ? null : JSON.stringify(result.body), { headers: { ETag: tag, 'Content-Type': 'application/json' } });
}
export const investigationHandlers = [http.get(`${investigationBase}/*`, respond), http.head(`${investigationBase}/*`, respond)];
