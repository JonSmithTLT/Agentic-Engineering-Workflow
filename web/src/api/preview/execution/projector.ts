import { executionFixture } from './fixtures';
import { executionCases } from './schema';
export const executionBase='/api/preview/execution/v0.1';
export const executionEnvelope=<T,>(data:T,project='aew-demo',revision='42')=>({schema_version:'0.1.0' as const,project_id:project,control_revision:revision,generated_at:'2026-10-04T12:00:00Z',data});
export class ExecutionProjector{
  private counts=new Map<string,number>();
  constructor(private dataset='demo'){}
  read(url:URL,project='aew-demo',revision='42'):{status:number;body?:unknown}{
    const p=url.searchParams,name=p.get('case')??'story',route=url.pathname.slice(executionBase.length);
    if(!executionCases.includes(name as typeof executionCases[number])||p.get('run_id')&&!p.get('invocation_id'))return{status:400};
    if(name==='denied')return{status:403};
    if(name==='historical-unavailable'&&route!=='/traces')return{status:410};
    const count=(this.counts.get(url.href)??0)+1;this.counts.set(url.href,count);
    if(name==='refresh-error'&&count>2)return{status:500};
    const f=executionFixture(name,project),send=(data:unknown)=>({status:200,body:executionEnvelope(data,project,revision)});
    let rows:unknown[]=[];
    const m=/^\/traces\/([^/]+)(?:\/(events|executions)(?:\/([^/]+)(?:\/(controls|receipts))?)?)?$/.exec(route);
    if(route==='/traces')rows=f.traces.filter(t=>(!p.get('work')||t.work.id===p.get('work'))&&(!p.get('invocation_id')||f.executions.some(e=>e.invocation?.id===p.get('invocation_id')&&(!p.get('run_id')||e.run_id===p.get('run_id')))));
    else if(m){const t=f.traces.find(t=>t.id===m[1]);if(!t)return{status:404};
      // Each fixed source has its own exact binding, even with repeated object IDs.
      const b={source_id:t.id,snapshot_id:t.snapshot_id,project_id:project};
      f.events.forEach(e=>e.binding={...b});f.executions.forEach(e=>{e.binding={...b};e.relations.forEach(r=>r.binding={...b});});f.controls.forEach(c=>c.binding={...b});if(name!=='mismatch')f.receipts.forEach(r=>r.binding={...b});
      if(!m[2])return send(t);
      if(m[2]==='events'){rows=f.events.filter(e=>(!p.get('lane')||e.lane===p.get('lane'))&&(!p.get('execution_id')||e.execution_id===p.get('execution_id')));if(m[3]){const e=f.events.find(e=>e.id===m[3]);return e?send(e):{status:404};}}
      else {const e=m[3]&&f.executions.find(e=>e.id===m[3]);if(m[3]&&!e)return{status:404};if(m[4]==='controls')return send(f.controls.find(c=>c.execution_id===m[3]));if(m[4]==='receipts')rows=f.receipts.filter(r=>r.execution_id===m[3]);else if(e)return send(e);else rows=f.executions;}
    }else return{status:404};
    const limit=Number(p.get('limit')??50);if(!Number.isInteger(limit)||limit<1||limit>50)return{status:400};
    const scope=JSON.stringify([this.dataset,project,revision,name,route,p.get('work'),p.get('invocation_id'),p.get('run_id'),p.get('lane'),p.get('execution_id'),limit]);let offset=0;
    if(p.get('cursor')){try{const[bound,pos]=JSON.parse(decodeURIComponent(p.get('cursor')!));if(bound!==scope||!Number.isInteger(pos)||pos<0||pos%limit!==0||p.get('cursor')!.length>8192)return{status:400};offset=pos;}catch{return{status:400};}}
    rows.sort((a,b)=>{const x=a as {id:string;ordinal?:number|null},y=b as typeof x;return m?.[2]==='events'?((x.ordinal??Infinity)-(y.ordinal??Infinity)||(x.id<y.id?-1:x.id>y.id?1:0)):(x.id<y.id?-1:x.id>y.id?1:0);});
    if(offset>rows.length)return{status:400};return send({items:rows.slice(offset,offset+limit),next_cursor:offset+limit<rows.length?encodeURIComponent(JSON.stringify([scope,offset+limit])):null});
  }
}
