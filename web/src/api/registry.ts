import { responseSchemas } from './schema';
import { additiveResponseSchemas } from './additive-schema';
import version from './contract-version.json';
import type { z } from 'zod';
export type ContractRegistration = {
  id: string;
  version: string;
  artifact: string;
  sha256: string;
  disposition: 'ACCEPTED' | 'PROVISIONAL';
  parsers: Record<string, z.ZodType>;
  fixtures: readonly string[];
  explanation_absence: 'EXPLICIT_WHEN_EXPLANATIONS_EXPOSED';
};
export const acceptedContract: ContractRegistration = {
  id: 'dashboard-api',
  version: version.version,
  artifact: 'docs/design/dashboard-api-v1-provisional.yaml',
  sha256: version.sha256,
  disposition: 'ACCEPTED',
  parsers: { ...responseSchemas, ...additiveResponseSchemas },
  fixtures: Array.from({ length: 12 }, (_, i) => `F${i}`),
  explanation_absence: 'EXPLICIT_WHEN_EXPLANATIONS_EXPOSED',
};
