import { http, HttpResponse } from 'msw';
import { selectedWorld } from '../../mock/worlds';
import { representationTag } from '../../mock/projector';
import { EvidenceProjector,evidenceBase } from './projector';
import type { EvidenceSource } from './schema';
const stores=new Map<string,EvidenceProjector>();
async function respond({request}:{request:Request}){
  const world=selectedWorld(),url=new URL(request.url),project=world.responses['/project'] as {project_id:string;control_revision:string};
  if(!stores.has(world.fixture))stores.set(world.fixture,new EvidenceProjector(world.fixture,((world.responses['/evidence'] as {data?:{items?:EvidenceSource['evidence'][]}})?.data?.items??[])));
  const result=stores.get(world.fixture)!.read(url,project.project_id,project.control_revision);
  if(result.status!==200)return new HttpResponse(null,{status:result.status});
  const tag=await representationTag(url,result.body);if(request.headers.get('If-None-Match')===tag)return new HttpResponse(null,{status:304,headers:{ETag:tag}});
  return new HttpResponse(request.method==='HEAD'?null:JSON.stringify(result.body),{headers:{ETag:tag,'Content-Type':'application/json'}});
}
export const evidenceHandlers=[http.get(`${evidenceBase}/*`,respond),http.head(`${evidenceBase}/*`,respond)];
