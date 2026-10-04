import { useEffect,useMemo,useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useDashboard } from '../../../client/dashboard';
import { useProjection,useReadSession,projectionKey } from '../../../client/queries';
import { ReadTransport,accessRefused } from '../../transport';
import { RequestLog } from '../../diagnostics';
import { readClock } from '../../../client/clock';
import { executionContract } from './registration';
import { executionSchemas,type Trace } from './schema';
import type { z } from 'zod';
export function useExecutionReader(owner:string,name:string,snapshot='chooser'){
 const base=useReadSession(),project=useDashboard().project.data?.value.project_id,client=useQueryClient();
 const reader=useMemo(()=>{const r=new ReadTransport(undefined,()=>readClock.now(),new RequestLog(),{base:'/api/preview/execution/v0.1',routes:/^\/traces(?:[/?]|$)/});r.reset({...base.identity,dataset:`${base.identity.dataset}:execution:${name}:${project}:${owner}`,contract:`provisional:0.1.0:${executionContract.sha256}`,snapshot});if(project)r.context.bind(project);return r;},[base,project,owner,name,snapshot]);
 useEffect(()=>()=>{reader.context.retire();const predicate=(q:{queryKey:readonly unknown[]})=>q.queryKey[1]===reader.context.key('/traces');void client.cancelQueries({predicate});client.removeQueries({predicate});},[reader,client]);
 useEffect(()=>{let clearing=false;return client.getQueryCache().subscribe(event=>{if(clearing||event.type!=='updated'||event.action.type!=='error'||event.query.queryKey[1]!==reader.context.key('/traces')||!accessRefused(event.query.state.error))return;clearing=true;reader.clearRepresentations();void client.cancelQueries({predicate:q=>q.queryKey[1]===reader.context.key('/traces')&&q.state.fetchStatus==='fetching'});for(const q of client.getQueryCache().findAll({predicate:q=>q.queryKey[1]===reader.context.key('/traces')})){if(q.state.data!==undefined)q.setState({data:undefined,error:event.query.state.error});}clearing=false;});},[reader,client]);
 return {reader,ready:!!project,project};
}
export function useTrace(name:string,sourceId:string,displayed=true){
 const discovery=useExecutionReader(`identity:${sourceId}`,name),[anchor,setAnchor]=useState<Trace|null>(null),[failure,setFailure]=useState<Error|null>(null),[retry,setRetry]=useState(0);
 const current=anchor?.id===sourceId?anchor:null,route=`/traces/${encodeURIComponent(sourceId)}?case=${encodeURIComponent(name)}`;
 useEffect(()=>{if(!discovery.ready||!sourceId||current||!displayed)return;const controller=new AbortController(),schema=executionSchemas.TraceResponse.superRefine(({data:t},c)=>{if(t.id!==sourceId)c.addIssue({code:'custom',message:'Trace identity mismatch'});});discovery.reader.get(route,schema,controller.signal).then(result=>{if(controller.signal.aborted)return;setAnchor(result.value.data);setFailure(null);discovery.reader.reset(discovery.reader.context.identity,false);discovery.reader.context.retire();}).catch(e=>{if(!controller.signal.aborted)setFailure(e);});return()=>controller.abort();},[discovery.ready,discovery.reader,sourceId,current,route,displayed,retry]);
 const bound=useExecutionReader(`trace:${sourceId}`,name,current?.snapshot_id??'unbound');
 const schema=useMemo(()=>executionSchemas.TraceResponse.superRefine(({data:t},c)=>{if(!current||t.id!==current.id||t.snapshot_id!==current.snapshot_id||t.project_id!==current.project_id)c.addIssue({code:'custom',message:'Fixed trace/snapshot binding mismatch'});}),[current]);
 const query=useProjection(route,schema,'history',!!current&&bound.ready,displayed,bound.reader,false);
 return {...query,error:query.error??failure,reader:bound.reader,refetch:()=>current?query.refetch():(setFailure(null),setRetry(n=>n+1))};
}
/** Pages replace bodies and validators; retained detail belongs to the reader, never to a page. */
export function useExecutionPage<T>(route:string,schema:z.ZodType<T>,reader:ReadTransport,displayed=true){
 const client=useQueryClient(),q=useProjection(route,schema,'history',true,displayed,reader,false);
 useEffect(()=>()=>{const key=projectionKey(route,reader);void client.cancelQueries({queryKey:key,exact:true});client.removeQueries({queryKey:key,exact:true});reader.forget(route);},[route,reader,client]);return q;
}
