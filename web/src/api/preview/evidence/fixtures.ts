import type { Association, Artifact, EvidenceSource, Origin } from './schema.ts';
// @ts-expect-error Pinned Node artifact runner.
import { sha256 } from './digest.ts';
export const journalDigest = '72f0cb0b1a675bf809f4b1f3026a322cfc0e8da20f5e6c3f53e162f2bda48df8';
export const investigationDigest = '79a1ac8460a8c4e39260c37c85197c16041f71e998023f039e292a2249bd436d';
export const acceptedDigest = '68b46527c4df974fde8ae5808e7d3c6bc588a4010a3d5d2adbe47f4c7583d691';
const ref = (id: string, kind: string, title: string | null = null) => ({id,kind,title});
export const referenceAssociations: Association[] = [
  ...[['CLANGD-E871','supporting','ES-Removal'],['CLANGD-E875','supporting','ES-Discovery'],['CLANGD-E880','opposing','ES-Counter']] .map(([evidence_id,role,source]) => ({ reference_id:`REF-J05-${evidence_id}`, origin:{contract:journalDigest,case:'story',record_id:'J-05',item_id:null,kind:'evidence_reference',role,evidence_id,source_id:null,snapshot_id:null,visibility_scope:'fictional-authorized'},source_ids:[source],complete:true })),
  {reference_id:'REF-PKT-Retry-E875',origin:{contract:investigationDigest,case:'story',record_id:'PKT-Retry',item_id:'PKT-Retry-CLANGD-E875',kind:'evidence_reference',role:'packet_item',evidence_id:'CLANGD-E875',source_id:'SRC-Retry',snapshot_id:'SNAP-Retry',visibility_scope:'fictional-authorized'},source_ids:['ES-Discovery'],complete:true},
  ...[['Removal','CLANGD-E871','ES-Removal'],['Retry','CLANGD-E875','ES-Discovery'],['Later','CLANGD-E875','ES-Discovery']].map(([label,evidence_id,source]) => ({reference_id:`REF-INV-${label}`,origin:{contract:investigationDigest,case:'story',record_id:`CLANGD-INV-${label}`,item_id:null,kind:'evidence_reference',role:'invocation_evidence',evidence_id,source_id:`SRC-${label}`,snapshot_id:`SNAP-${label}`,visibility_scope:'fictional-authorized'},source_ids:[source],complete:true})),
  {reference_id:'REF-J05-E875-Historical',origin:{contract:journalDigest,case:'history-fixture',record_id:'J-05',item_id:null,kind:'evidence_reference',role:'supporting',evidence_id:'CLANGD-E875',source_id:null,snapshot_id:'SNAP-Old',visibility_scope:'historical-authorized'},source_ids:['ES-Discovery-Old'],complete:true},
];
export function sameOrigin(a: Origin,b: Origin) { return Object.keys(a).length===Object.keys(b).length && Object.entries(a).every(([key,value])=>b[key as keyof Origin]===value); }
export function findAssociation(expected: Origin) { return referenceAssociations.find(a => sameOrigin(a.origin,expected)); }
export function evidenceFixture(name = 'story', accepted: EvidenceSource['evidence'][] = []) {
  const sources: EvidenceSource[] = [], artifacts: Artifact[] = [], bodies: Record<string,string> = {};
  const add = (label:string, eid:string, claim:string, text:string, media='text/x-log') => {
    const source_id=`ES-${label}`, snapshot_id=`EV-SNAP-${label}`;
    const source:EvidenceSource = {id:source_id,evidence_id:eid,snapshot_id,captured_at:label === 'Removal' ? '2026-10-02T16:20:00Z' : label === 'Discovery' ? '2026-10-02T16:30:00Z' : '2026-10-02T16:35:00Z',visibility_scope:'fictional-authorized',source_revision:label === 'Removal' ? 'stale-db-fictional':'refreshed-db-fictional',work:ref('CLANGD-T181','work_reference','Investigate missing callers'),artifacts_complete:true,canonical_references:[ref('CLANGD-D42','decision_reference','Generated protocol definitions remain source-controlled')],evidence:{id:eid,kind:'verification',result:label === 'Removal'?'fail':'pass',subject:ref('CLANGD-T181','work_reference'),currentness:'CURRENT',requires_disposition:false,claim:{format:'plain',text:claim},body:{format:'plain',text:'Fictional supplied evidence. Artifacts are a bounded projection, not proof of complete coverage or causal benefit.'},findings:[],deviations:[],bindings:{evaluated_snapshot:{base_revision:label === 'Removal'?'stale-db-fictional':'refreshed-db-fictional',relevant_inputs_fingerprint:`fictional-${label}`,artifact_digests:['opaque-artifact:'+sha256(text)]},plan_revision:null,producer:{role:'investigator',invocation:label === 'Removal'?'CLANGD-INV-Removal':label === 'Discovery'?'CLANGD-INV-Discovery':'CLANGD-INV-Counter',run:label === 'Removal'?'CLANGD-R-A2-2':label === 'Discovery'?'CLANGD-R-A2-3':'CLANGD-R-COUNTER',model:null,provider:null,harness:'fictional-harness'}},provenance:[ref('J-04','journal')]}};
    sources.push(source);
    const a:Artifact={id:`ART-${label}`,source_id,evidence_id:eid,snapshot_id,revision:'1',display_name:`${label} supplied diagnostic`,media_type:media,encoding:'UTF-8',full_digest:'sha256:'+sha256(text),size_bytes:new TextEncoder().encode(text).length,availability:'AVAILABLE',explanation:null,coverage_complete:true,omitted_ranges:[]}; artifacts.push(a);bodies[`${source_id}:${a.id}`]=text;
    return source;
  };
  add('Removal','CLANGD-E871','Removal broke generated protocol callers; the change was reverted.','[fictional build]\ngenerated/protocol_client.cpp:42: undefined reference to dispatch_protocol\nbuild result: FAIL\nRemoval reverted. Missing index references did not establish unused code.\n');
  add('Discovery','CLANGD-E875','Refreshing compilation data revealed generated callers.','{"fictional":true,"compilation_database":"refreshed","revision":"refreshed-db-fictional","callers":["generated/protocol_client.cpp:42"],"observation":"Generated caller now appears in clangd references"}\n','application/json');
  add('Counter','CLANGD-E880','A fresh database can also confirm genuinely unused functions; absence alone is insufficient.','// Fictional counterexample: generated_unused_helper\n// Fresh compilation data and independent build inspection report no callers.\n// This limits the lesson; refreshing data does not guarantee callers exist.\n','text/x-code');
  const old=structuredClone(sources[1]);old.id='ES-Discovery-Old';old.snapshot_id='EV-SNAP-Old';old.visibility_scope='historical-authorized';old.evidence.currentness='STALE';old.captured_at='2026-10-02T16:30:00Z';sources.push(old);
  for (const e of accepted) sources.push({...structuredClone(sources[0]),id:`ES-${e.id}`,evidence_id:e.id,snapshot_id:`EV-${e.id}`,evidence:structuredClone(e),work:e.subject,source_revision:e.bindings.evaluated_snapshot?.base_revision ?? null,artifacts_complete:false,canonical_references:[]});
  if(name==='large') { const base=artifacts[0],text='Fictional long diagnostic ☃ 😀\n'.repeat(3000); for(let i=0;i<125;i++){ const a={...base,id:`ART-${String(i).padStart(3,'0')}`,full_digest:'sha256:'+sha256(text),size_bytes:new TextEncoder().encode(text).length};artifacts.push(a);bodies[`${a.source_id}:${a.id}`]=text; } }
  if(name==='hostile') {const text='\u001b[31mANSI\u001b[0m\nBidi: \u202Ehidden\u202C\nInvisible: a\u200Bb\u2066isolated\u2069\n<script>globalThis.evidenceAttack=true</script>\n';bodies['ES-Removal:ART-Removal']=text;Object.assign(artifacts[0],{full_digest:'sha256:'+sha256(text),size_bytes:new TextEncoder().encode(text).length});}
  if(name==='missing') artifacts.splice(0);
  if(name==='partial') {sources[0].artifacts_complete=false;artifacts[0].availability='UNAVAILABLE';artifacts[0].explanation=null;artifacts[0].coverage_complete=false;artifacts[0].omitted_ranges=[{byte_start:0,byte_end:artifacts[0].size_bytes!,explanation:null}];}
  if(name==='unknown') {sources[0].evidence.result='FUTURE_RESULT';artifacts[0].availability='FUTURE_AVAILABILITY';artifacts[0].media_type='future/media';}
  if(name==='unsupported') artifacts[0].media_type='application/pdf';
  if(name==='stale') sources[0].evidence.currentness='STALE';
  if(name==='malformed') (sources[0].evidence as unknown as Record<string,unknown>).raw_prompt='excluded';
  if(name==='binding-mismatch') artifacts[0].evidence_id='WRONG-EVIDENCE';
  if(name==='empty') sources.splice(0);
  return {sources,artifacts,bodies,associations:structuredClone(referenceAssociations)};
}
