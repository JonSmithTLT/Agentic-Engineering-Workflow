import { http, HttpResponse } from 'msw';
import { JournalProjector, previewBase } from './projector';
import { selectedWorld } from '../../mock/worlds';
const projector = new JournalProjector();
const counts = new Map<string, number>();
async function respond({ request }: {
    request: Request;
}) {
    const url = new URL(request.url), world = selectedWorld();
    const project = world.responses['/project'] as {
        project_id: string;
        control_revision: string;
    };
    const key = url.href, count = (counts.get(key) ?? 0) + 1;
    counts.set(key, count);
    if (url.searchParams.get('case') === 'refresh-error' && count > 1)
        return new HttpResponse(null, { status: 500 });
    const result = projector.read(url, project.project_id, project.control_revision);
    if (result.status !== 200)
        return new HttpResponse(null, { status: result.status });
    const bytes = new TextEncoder().encode(JSON.stringify(result.body));
    const hash = await crypto.subtle.digest('SHA-256', bytes);
    const etag = '"' + Array.from(new Uint8Array(hash), (b) => b.toString(16).padStart(2, '0')).join('') + '"';
    if (request.headers.get('If-None-Match') === etag)
        return new HttpResponse(null, { status: 304, headers: { ETag: etag } });
    return request.method === 'HEAD' ? new HttpResponse(null, { headers: { ETag: etag } }) : new HttpResponse(JSON.stringify(result.body), { headers: { ETag: etag, 'Content-Type': 'application/json' } });
}
export const journalHandlers = [http.get(`${previewBase}/*`, respond), http.head(`${previewBase}/*`, respond)];
