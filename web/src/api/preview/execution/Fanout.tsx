import { useEffect,useRef,useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { projectionKey } from '../../../client/queries';
import { executionSchemas,executionIssue,hierarchyKinds,relationKinds,type Execution,type Trace } from './schema';
import { SemanticValue } from '../../../components/States';
import { ErrorState } from '../investigation/ui';
import { accessRefused,type ReadTransport } from '../../transport';
export const partiality='Only loaded supplied relationships are displayed within the bounds. Absence of a child is not evidence that none exists.';
export function boundedHierarchy(root:string,loaded:Map<string,Execution>){
 const rows:{id:string;depth:number;label:string;terminal:boolean;path:string[];source:string|null}[]=[],correlations:{from:string;to:string;source:string}[]=[];let edges=0;
 function visit(id:string,depth:number,path:string[],label:string,source:string|null,terminal=false){
  if(rows.length>=24)return;const cycle=path.includes(id);rows.push({id,depth,label:cycle?`${label} · Cycle reference`:label,terminal:terminal||cycle||depth>=3,path,source});
  const e=loaded.get(id);if(!e||cycle||terminal||depth>=3)return;
  for(const r of e.relations){if(edges>=80||rows.length>=24)break;edges++;if(r.relation_kind==='trace_correlation'){correlations.push({from:r.from.id,to:r.to.id,source:r.source.id});continue;}visit(r.to.id,depth+1,[...path,id],r.relation_kind,r.source.id,r.to.kind!=='execution'||!hierarchyKinds.includes(r.relation_kind));}
 }
 visit(root,0,[],'Trace root',null);return {rows,correlations,edges};
}
export function FanoutHierarchy({trace,name,reader,select}:{trace:Trace;name:string;reader:ReadTransport;select:(id:string)=>void}){
 const client=useQueryClient();
 const [loaded,setLoaded]=useState(new Map<string,Execution>()),[error,setError]=useState<unknown>(),[pending,setPending]=useState(''),[failedId,setFailedId]=useState('');
 const controllers=useRef(new Set<AbortController>());
 useEffect(()=>()=>{controllers.current.forEach(c=>c.abort());},[reader]);
 const tree=boundedHierarchy(trace.root_execution,loaded);
 async function expand(id:string){
  if(loaded.size>=24||loaded.has(id))return;const controller=new AbortController();controllers.current.add(controller);setPending(id);setError(undefined);setFailedId('');
  try{const schema=executionSchemas.ExecutionResponse.superRefine(({data:e},c)=>{const issue=executionIssue(e,trace);if(e.id!==id||issue)c.addIssue({code:'custom',message:issue??'Execution identity mismatch'});});const route=`/traces/${trace.id}/executions/${id}?case=${name}`;const result=await client.fetchQuery({queryKey:projectionKey(route,reader),meta:{automaticRevalidation:false},staleTime:Infinity,queryFn:({signal})=>reader.get(route,schema,AbortSignal.any([signal,controller.signal]))});if(!controller.signal.aborted)setLoaded(old=>new Map(old).set(id,result.value.data));}catch(e){if(!controller.signal.aborted){if(accessRefused(e)){reader.clearRepresentations();setLoaded(new Map());}setFailedId(id);setError(e);}}finally{controllers.current.delete(controller);if(!controller.signal.aborted)setPending('');}
 }
 return <section className="panel execution-fanout"><h3>Supplied typed hierarchy</h3><p>The hierarchy is a view over supplied typed relations, not their canonical meaning. Correlation is not parentage, custody or causation.</p><p>{partiality}</p><p>Bounds: 3 levels · 24 nodes · 80 edges. Browser-loaded nodes: {loaded.size}; displayed nodes: {tree.rows.length}; supplied edges shown: {tree.edges}.</p>{!!error&&<ErrorState error={error} retry={()=>void expand(failedId||trace.root_execution)}/>}
 <ul className="execution-tree">{tree.rows.map((r,index)=><li key={`${index}:${r.id}`} className={`execution-depth-${r.depth}`}><SemanticValue value={r.label} known={['Trace root',...relationKinds,...relationKinds.map(k=>`${k} · Cycle reference`)]}/> · <code>{r.id}</code>{r.source&&<small> · Supplied source {r.source}</small>}{r.terminal?<span> · Terminal reference / expansion bound</span>:<><button onClick={()=>select(r.id)}>Inspect {r.id}</button>{!loaded.has(r.id)&&<button disabled={!!pending} onClick={()=>void expand(r.id)}>Expand {r.id}</button>}</>}{loaded.get(r.id)&&<small> · {loaded.get(r.id)!.registration_state} · {loaded.get(r.id)!.relations_complete?'Complete supplied relationships':'Incomplete supplied relationships'}</small>}</li>)}</ul>
 <h4>Correlation-only references</h4>{tree.correlations.length?<ul>{tree.correlations.map((r,i)=><li key={i}>{r.from} ↔ {r.to} · trace_correlation · Supplied source {r.source}</li>)}</ul>:<p>No correlation links loaded. Absence does not establish none exist.</p>}
 </section>;
}
