import manifest from '../../../../docs/design/investigation-fixtures.manifest.json';
import type { ContractRegistration } from '../../registry';
import { investigationSchemas } from './schema';
export const investigationContract: ContractRegistration = {
  id: 'investigation-preview', version: '0.1.0', artifact: 'web/docs/design/investigation-preview-0.1.0.json', sha256: manifest.sha256,
  disposition: 'PROVISIONAL', parsers: investigationSchemas, fixtures: Object.keys(manifest.cases), explanation_absence: 'EXPLICIT_WHEN_EXPLANATIONS_EXPOSED',
};
