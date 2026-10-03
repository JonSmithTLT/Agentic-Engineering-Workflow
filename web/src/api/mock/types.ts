export type World = {
  fixture: string;
  name: string;
  contract_version: string;
  contract_sha256: string;
  responses: Record<string, unknown>;
  models: Record<string, string>;
  pages: Record<string, unknown>;
  page_models: Record<string, string>;
  scenarios: { kind: string; [key: string]: unknown }[];
  provisional_responses: Record<string, unknown>;
  provisional_models: Record<string, string>;
};
