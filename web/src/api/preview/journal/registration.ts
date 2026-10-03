import manifest from '../../../../docs/design/journal-fixtures.manifest.json';
import type { ContractRegistration } from '../../registry';
import { journalSchemas } from './schema';
export const journalContract: ContractRegistration = {
    id: 'journal-preview', version: '0.1.0', artifact: 'web/docs/design/journal-preview-0.1.0.json', sha256: manifest.sha256,
    disposition: 'PROVISIONAL', parsers: journalSchemas, fixtures: Object.keys(manifest.cases), explanation_absence: 'EXPLICIT_WHEN_EXPLANATIONS_EXPOSED',
};
