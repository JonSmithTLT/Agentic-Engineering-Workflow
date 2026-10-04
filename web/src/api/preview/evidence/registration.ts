import manifest from '../../../../docs/design/evidence-fixtures.manifest.json';
import type { ContractRegistration } from '../../registry';
import { evidenceSchemas } from './schema';
export const evidenceContract:ContractRegistration={id:'evidence-preview',version:'0.1.0',artifact:'web/docs/design/evidence-preview-0.1.0.json',sha256:manifest.sha256,disposition:'PROVISIONAL',parsers:evidenceSchemas,fixtures:Object.keys(manifest.cases),explanation_absence:'EXPLICIT_WHEN_EXPLANATIONS_EXPOSED'};
