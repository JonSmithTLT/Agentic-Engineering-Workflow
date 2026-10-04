// Presentation-only extension registry. Existing preview wire models and fixture identities stay intact.
import manifest from '../../../../docs/design/execution-fixtures.manifest.json' with {type:'json'};
// @ts-expect-error Pinned Node projector loader.
import { referenceAssociations,sameOrigin } from './fixtures.ts';
import type { Association,Origin,EvidenceSource } from './schema';
export const inspectionAssociations:Association[]=[...referenceAssociations,...manifest.evidence_associations];
export function inspectionAssociation(origin:Origin){return inspectionAssociations.find(a=>sameOrigin(a.origin,origin));}

export function inspectionTarget(referenceId:string){return manifest.mappings.find(m=>m.target.contract==='evidence-preview'&&m.target.reference_id===referenceId)?.target;}
export function inspectionTargetIssue(s:EvidenceSource,t:ReturnType<typeof inspectionTarget>){return t&&(s.id!==t.source_id||s.snapshot_id!==t.snapshot_id||s.visibility_scope!==t.visibility_scope||s.evidence.id!==t.record_id||s.evidence.bindings.producer?.invocation!==t.invocation_id||s.evidence.bindings.producer?.run!==t.run_id)?'Cross-preview Evidence source/snapshot/run binding mismatch':undefined;}
