import { z } from 'zod';
export const scenarioVersion = '1.0.0';
export const scenarioConfig = z.strictObject({
  catalog: z.literal(scenarioVersion),
  recipe: z.string().regex(/^[a-z][a-z0-9-]{0,63}$/),
  fixture: z.string().regex(/^F(?:[0-9]|1[01])$/),
  seed: z.number().int().min(0).max(4294967295),
});
export type ScenarioConfig = z.infer<typeof scenarioConfig>;
export const generatedScenarioSchema = () => z.toJSONSchema(scenarioConfig);
