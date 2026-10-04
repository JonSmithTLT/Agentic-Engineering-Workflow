import { useEffect,useMemo,useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useDashboard } from '../../../client/dashboard';
import { useProjection,useReadSession,projectionKey } from '../../../client/queries';
import { ReadTransport,accessRefused } from '../../transport';
import { RequestLog } from '../../diagnostics';
import { readClock } from '../../../client/clock';
import { evidenceContract } from './registration';
import { evidenceSchemas,sourceIssue,type EvidenceSource } from './schema';
import {inspectionTargetIssue,type inspectionTarget} from './associations';
export function useEvidenceReader(owner:string,name:string,snapshot='chooser',visibility='unresolved'){
  const base=useReadSession(),project=useDashboard().project.data?.value.project_id,client=useQueryClient();
  const reader=useMemo(()=>{const r=new ReadTransport(undefined,()=>readClock.now(),new RequestLog(),{base:'/api/preview/evidence/v0.1',routes:/^\/(?:references|sources)(?:[/?]|$)/});r.reset({...base.identity,dataset:`${base.identity.dataset}:evidence:${name}:${owner}:${visibility}`,contract:`provisional:0.1.0:${evidenceContract.sha256}`,snapshot});if(project)r.context.bind(project);return r;},[base,project,owner,name,snapshot,visibility]);
  useEffect(()=>()=>{reader.context.retire();const key=reader.context.key('/sources'),predicate=(q:{queryKey:readonly unknown[]})=>q.queryKey[1]===key;void client.cancelQueries({predicate});client.removeQueries({predicate});},[reader,client]);
  useEffect(()=>{let clearing=false;return client.getQueryCache().subscribe(event=>{if(clearing||event.type!=='updated'||event.action.type!=='error'||!('query' in event)||event.query.queryKey[1]!==reader.context.key('/sources')||!accessRefused(event.query.state.error))return;clearing=true;reader.clearRepresentations();void client.cancelQueries({predicate:q=>q.queryKey[1]===reader.context.key('/sources')&&q.state.fetchStatus==='fetching'});for(const q of client.getQueryCache().findAll({predicate:q=>q.queryKey[1]===reader.context.key('/sources')})){if(q.state.data!==undefined)q.setState({data:undefined,error:event.query.state.error});}clearing=false;});},[reader,client]);
  return {reader,ready:!!project};
}
export function useEvidenceSource(name:string,sourceId:string,expected?:ReturnType<typeof inspectionTarget>){
  const discovery=useEvidenceReader(`identity:${sourceId}`,name),[anchor,setAnchor]=useState<{id:string;snapshot:string;visibility:string}|null>(null),[failure,setFailure]=useState<Error|null>(null),[retry,setRetry]=useState(0);
  const current=anchor?.id===sourceId?anchor:null,route=`/sources/${encodeURIComponent(sourceId)}?case=${encodeURIComponent(name)}`;
  useEffect(()=>{if(!discovery.ready||!sourceId||current)return;const controller=new AbortController();const schema=evidenceSchemas.EvidenceSourceResponse.superRefine(({data:s},ctx)=>{if(s.id!==sourceId||sourceIssue(s)||inspectionTargetIssue(s,expected))ctx.addIssue({code:'custom',message:'Evidence source binding mismatch'});});discovery.reader.get(route,schema,controller.signal).then(result=>{if(controller.signal.aborted)return;const s=result.value.data;setAnchor({id:s.id,snapshot:s.snapshot_id,visibility:s.visibility_scope});setFailure(null);discovery.reader.reset(discovery.reader.context.identity,false);discovery.reader.context.retire();}).catch(error=>{if(!controller.signal.aborted)setFailure(error);});return()=>controller.abort();},[discovery.ready,discovery.reader,sourceId,current,route,retry,expected]);
  const bound=useEvidenceReader(`source:${sourceId}`,name,current?.snapshot??'unbound',current?.visibility);
  const schema=useMemo(()=>evidenceSchemas.EvidenceSourceResponse.superRefine(({data:s},ctx)=>{if(s.id!==sourceId||s.snapshot_id!==current?.snapshot||s.visibility_scope!==current?.visibility||sourceIssue(s)||inspectionTargetIssue(s,expected))ctx.addIssue({code:'custom',message:'Evidence source/snapshot binding mismatch'});}),[sourceId,current,expected]);
  const query=useProjection(route,schema,'history',!!current&&bound.ready,true,bound.reader,false);
  return {...query,error:query.error??failure,reader:bound.reader,refetch:()=>current?query.refetch():(setFailure(null),setRetry(n=>n+1))};
}
export function useBoundedExcerpt(route:string,schema:typeof evidenceSchemas.ExcerptResponse,reader:ReadTransport){
  const client=useQueryClient(),query=useProjection(route,schema,'history',true,true,reader,false);
  useEffect(()=>()=>{const key=projectionKey(route,reader);void client.cancelQueries({queryKey:key,exact:true});client.removeQueries({queryKey:key,exact:true});reader.forget(route);},[route,reader,client]);
  return query;
}
export type SourceQuery=ReturnType<typeof useEvidenceSource>;
export function artifactBinding(s:EvidenceSource,id:string,revision:string){return `${s.id}:${s.snapshot_id}:${s.visibility_scope}:${id}:${revision}`;}
