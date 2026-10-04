import { evidenceFixture } from './fixtures';
import { evidenceCases, type EvidenceSource } from './schema';
import { sha256 } from './digest';
export const evidenceBase='/api/preview/evidence/v0.1';
export const evidenceEnvelope=<T,>(data:T,project='aew-demo',revision='42')=>({schema_version:'0.1.0' as const,project_id:project,control_revision:revision,generated_at:'2026-10-03T12:00:00Z',data});
export class EvidenceProjector {
  private counts=new Map<string,number>();
  constructor(private dataset='demo',private accepted:EvidenceSource['evidence'][]=[]){}
  read(url:URL,project='aew-demo',revision='42'):{status:number;body?:unknown}{
    const p=url.searchParams,name=p.get('case')??'story',route=url.pathname.slice(evidenceBase.length);
    if(!evidenceCases.includes(name as typeof evidenceCases[number]))return {status:400};
    if(name==='denied')return {status:403};
    if(name==='not-found')return {status:404};
    if(name==='historical-unavailable'&&route!=='/sources')return {status:410};
    const n=(this.counts.get(url.href)??0)+1;this.counts.set(url.href,n);
    if(['refresh-error','stale'].includes(name)&&n>(/^\/sources\/[^/]+$/.test(route)?2:1))return {status:500};
    const f=evidenceFixture(name,this.accepted),send=(data:unknown)=>({status:200,body:evidenceEnvelope(data,project,revision)});
    const rm=/^\/references\/([^/]+)$/.exec(route);
    if(rm){const a=f.associations.find(a=>a.reference_id===rm[1]);return a?send(a):{status:404};}
    const m=/^\/sources\/([^/]+)(?:\/artifacts(?:\/([^/]+)\/excerpt)?)?$/.exec(route);
    const source=m&&f.sources.find(s=>s.id===m[1]);if(m&&!source)return {status:404};
    if(m&&route===`/sources/${m[1]}`)return send(source);
    if(m?.[2]){
      const a=f.artifacts.find(a=>a.id===m[2]&&a.source_id===m[1]);if(!a||a.revision!==p.get('artifact_revision'))return {status:404};
      if(a.availability!=='AVAILABLE'||!['text/plain','text/x-code','text/x-log','text/markdown','application/json'].includes(a.media_type))return {status:415};
      const body=f.bodies[`${a.source_id}:${a.id}`],bytes=new TextEncoder().encode(body),scope=JSON.stringify([this.dataset,project,revision,name,a.source_id,a.id,a.revision]);let start=0;
      if(p.get('cursor')){try{const [bound,pos]=JSON.parse(decodeURIComponent(p.get('cursor')!));if(bound!==scope||!Number.isInteger(pos)||pos<0||pos>=bytes.length||p.get('cursor')!.length>8192||((bytes[pos]&192)===128))return {status:400};start=pos;}catch{return {status:400};}}
      let end=Math.min(start+16384,bytes.length);while(end<bytes.length&&(bytes[end]&192)===128)end--;
      const text=new TextDecoder('utf-8',{fatal:true}).decode(bytes.slice(start,end)),next=end<bytes.length?encodeURIComponent(JSON.stringify([scope,end])):null;
      return send({source_id:a.source_id,evidence_id:a.evidence_id,snapshot_id:a.snapshot_id,artifact_id:a.id,artifact_revision:a.revision,cursor:p.get('cursor'),text,byte_start:start,byte_end:end,line_start:1+new TextDecoder().decode(bytes.slice(0,start)).split('\n').length-1,line_end:1+new TextDecoder().decode(bytes.slice(0,end)).split('\n').length-1,sha256:name==='hash-mismatch'?'0'.repeat(64):sha256(text),truncated:start>0||end<bytes.length,scope:'Supplied fictional artifact projection only; no completeness or causal conclusion.',complete_value:start===0&&end===bytes.length,next_cursor:next});
    }
    if(route!=='/sources'&&!(m&&route.endsWith('/artifacts')))return {status:404};
    const limit=Number(p.get('limit')??50);if(!Number.isInteger(limit)||limit<1||limit>50)return {status:400};
    const scope=JSON.stringify([this.dataset,project,revision,name,route,p.get('evidence_id'),p.get('work'),p.get('reference_id'),p.get('artifact_id'),limit]);let offset=0;
    if(p.get('cursor')){try{const [bound,pos]=JSON.parse(decodeURIComponent(p.get('cursor')!));if(bound!==scope||!Number.isInteger(pos)||pos<0||pos%limit!==0||p.get('cursor')!.length>8192)return {status:400};offset=pos;}catch{return {status:400};}}
    const resolved=p.get('reference_id')?f.associations.find(a=>a.reference_id===p.get('reference_id')):null;
    if(p.get('reference_id')&&!resolved)return {status:404};
    const rows=(m?f.artifacts.filter(a=>a.source_id===source!.id&&(!p.get('artifact_id')||a.id===p.get('artifact_id'))):f.sources.filter(s=>(!resolved||resolved.source_ids.includes(s.id))&&(!p.get('evidence_id')||s.evidence_id===p.get('evidence_id'))&&(!p.get('work')||s.work.id===p.get('work')))).sort((a,b)=>a.id<b.id?-1:a.id>b.id?1:0);
    if(offset>rows.length)return {status:400};const items=rows.slice(offset,offset+limit).map(v=>m?v:{id:(v as EvidenceSource).id,evidence_id:(v as EvidenceSource).evidence_id,snapshot_id:(v as EvidenceSource).snapshot_id,captured_at:(v as EvidenceSource).captured_at,visibility_scope:(v as EvidenceSource).visibility_scope,source_revision:(v as EvidenceSource).source_revision,work:(v as EvidenceSource).work});
    return send({items,next_cursor:offset+limit<rows.length?encodeURIComponent(JSON.stringify([scope,offset+limit])):null});
  }
}
