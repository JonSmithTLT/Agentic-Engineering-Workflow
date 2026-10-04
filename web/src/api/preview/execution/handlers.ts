import { http,HttpResponse } from 'msw';
import { selectedWorld } from '../../mock/worlds';
import { representationTag } from '../../mock/projector';
import { ExecutionProjector,executionBase } from './projector';
const stores=new Map<string,ExecutionProjector>();
async function respond({request}:{request:Request}){
 const world=selectedWorld(),url=new URL(request.url),p=world.responses['/project'] as {project_id:string;control_revision:string};
 if(!stores.has(world.fixture))stores.set(world.fixture,new ExecutionProjector(world.fixture));
 const result=stores.get(world.fixture)!.read(url,p.project_id,p.control_revision);
 if(result.status!==200)return new HttpResponse(null,{status:result.status});
 const tag=await representationTag(url,result.body);if(request.headers.get('If-None-Match')===tag)return new HttpResponse(null,{status:304,headers:{ETag:tag}});
 return new HttpResponse(request.method==='HEAD'?null:JSON.stringify(result.body),{headers:{ETag:tag,'Content-Type':'application/json'}});
}
export const executionHandlers=[http.get(`${executionBase}/*`,respond),http.head(`${executionBase}/*`,respond)];
