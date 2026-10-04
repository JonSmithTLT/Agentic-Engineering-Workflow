import fs from 'node:fs';
import crypto from 'node:crypto';
import { z } from 'zod';
import { wireSchemas, executionSchemas, executionCases } from '../src/api/preview/execution/schema.ts';
import { vocabularyInventory } from '../src/api/preview/execution/vocabulary.ts';
import { executionFixture } from '../src/api/preview/execution/fixtures.ts';
const write=process.argv.includes('--write'),sha=t=>crypto.createHash('sha256').update(t).digest('hex');
function artifact(file,v){const text=JSON.stringify(v,null,2)+'\n';if(write)fs.writeFileSync(file,text);else if(fs.readFileSync(file,'utf8')!==text)throw Error(`Execution artifact drift: ${file}`);return sha(text);}
const rules=[
 'Execution preview events, ordinals, lane classes and trace relationships are presentation-fixture semantics only. They do not define the future transaction-outbox/event schema, ordering authority, correlation model or retention contract. Live/backend adoption is blocked on the accepted T3 event/outbox design and must use an explicit adapter/projection.',
 'Project-only visibility: visibility_scope equals the selected project. Opaque cross-preview scopes are provenance bindings, never authorization.',
 'Budget observations do not define cost-ledger fields, budget.remaining, enforcement or DispatchDecision semantics. G7/F7 requires an explicit adapter.',
 'Order ordinal ASC, id ASC; null ordinals in final Unordered group, id ASC. Timestamps never substitute. Ordinal discontinuities do not establish gaps.',
 'Hierarchy is a view over supplied typed relations, not their canonical meaning. Correlation never establishes parentage, custody or causation.',
 'Configured, available, authorized, active and successfully tested remain independent supplied claims. No browser fallback labels.',
 'Captured invocation status is not status at an event. No reconstructed state, polling, prefetch or inferred enforcement.',
 'Raw prompts, credentials, executable arguments, tool bodies and storage locations are excluded.',
];
const digest=artifact('docs/design/execution-preview-0.1.0.json',{id:'execution-preview',version:'0.1.0',disposition:'PROVISIONAL',routes:{base:'/api/preview/execution/v0.1',methods:['GET','HEAD'],paths:['/traces','/traces/{source_id}','/traces/{source_id}/events','/traces/{source_id}/events/{event_id}','/traces/{source_id}/executions','/traces/{source_id}/executions/{execution_id}','/traces/{source_id}/executions/{execution_id}/controls','/traces/{source_id}/executions/{execution_id}/receipts'],parameters:['case','work','invocation_id','run_id (requires invocation_id)','lane','execution_id','cursor','limit=1..50']},bounds:{page:50,lanes:32,dimensions:32,budgets:16,relations:80,expansion_levels:3,expansion_nodes:24,expansion_edges:80},rules,vocabulary:vocabularyInventory,schemas:Object.fromEntries(Object.entries(wireSchemas).map(([k,s])=>[k,z.toJSONSchema(s)]))});
const origin=(record_id,item_id=null)=>({contract:digest,case:'story',record_id,item_id,project_id:'aew-demo',source_id:'TRACE-Clangd',snapshot_id:'TRACE-SNAP-1'});
const mappings=[
 {id:'LOC-Failure',origin:origin('EV-03'),target:{contract:'evidence-preview',case:'story',reference_id:'REF-EXEC-Failure',source_id:'ES-Removal',snapshot_id:'EV-SNAP-Removal',invocation_id:'CLANGD-INV-Removal',run_id:'CLANGD-R-A2-2',record_id:'CLANGD-E871',visibility_scope:'fictional-authorized'}},
 {id:'LOC-Discovery',origin:origin('EV-04'),target:{contract:'evidence-preview',case:'story',reference_id:'REF-EXEC-Discovery',source_id:'ES-Discovery',snapshot_id:'EV-SNAP-Discovery',invocation_id:'CLANGD-INV-Discovery',run_id:'CLANGD-R-A2-3',record_id:'CLANGD-E875',visibility_scope:'fictional-authorized'}},
 ...['EV-05','EV-06','EV-07'].map(record_id=>({id:'LOC-RetryPacket',origin:origin(record_id),target:{contract:'investigation-preview',case:'story',reference_id:null,source_id:'SRC-Retry',snapshot_id:'SNAP-Retry',invocation_id:'CLANGD-INV-Retry',run_id:'CLANGD-R-A2-4',record_id:'PKT-Retry',visibility_scope:'fictional-authorized'}})),
];
const evidence_associations=mappings.filter(m=>m.target.contract==='evidence-preview').map(m=>({reference_id:m.target.reference_id,origin:{contract:digest,case:m.origin.case,record_id:m.origin.record_id,item_id:m.origin.item_id,kind:'evidence_reference',role:'recorded_event',evidence_id:m.target.record_id,source_id:m.origin.source_id,snapshot_id:m.origin.snapshot_id,visibility_scope:m.origin.project_id},source_ids:[m.target.source_id],complete:true}));
artifact('docs/design/execution-fixtures.manifest.json',{contract:'execution-preview',version:'0.1.0',sha256:digest,cases:Object.fromEntries(executionCases.map(n=>[n,{sha256:sha(JSON.stringify(executionFixture(n)))}])),mappings,evidence_associations});
const f=executionFixture();for(const t of f.traces)executionSchemas.TraceResponse.parse({schema_version:'0.1.0',project_id:'aew-demo',control_revision:'42',generated_at:'2026-10-04T12:00:00Z',data:t});
console.log('Execution preview artifacts and fixture identities match');
