// Presentation-only extension registry. Existing preview wire models and fixture identities stay intact.
import manifest from '../../../../docs/design/execution-fixtures.manifest.json' with {type:'json'};
// @ts-expect-error Pinned Node projector loader.
import { referenceAssociations,sameOrigin } from './fixtures.ts';
import type { Association,Origin } from './schema';
export const inspectionAssociations:Association[]=[...referenceAssociations,...manifest.evidence_associations];
export function inspectionAssociation(origin:Origin){return inspectionAssociations.find(a=>sameOrigin(a.origin,origin));}

export function inspectionTarget(referenceId:string){return manifest.mappings.find(m=>m.target.contract==='evidence-preview'&&m.target.reference_id===referenceId)?.target;}
