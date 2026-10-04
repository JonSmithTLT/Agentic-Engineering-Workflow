import manifest from '../../../../docs/design/execution-fixtures.manifest.json';
import type { ContractRegistration } from '../../registry';
import { executionSchemas } from './schema';
export const executionContract:ContractRegistration={id:'execution-preview',version:'0.1.0',artifact:'web/docs/design/execution-preview-0.1.0.json',sha256:manifest.sha256,disposition:'PROVISIONAL',parsers:executionSchemas,fixtures:Object.keys(manifest.cases),explanation_absence:'EXPLICIT_WHEN_EXPLANATIONS_EXPOSED'};
