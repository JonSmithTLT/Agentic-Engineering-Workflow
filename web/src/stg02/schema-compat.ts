// The sealed schemas use draft-07 assertions plus minContains:1. Compile them
// offline with the installed Ajv 6; never compile schemas in the browser (CSP).
export function compatibleSchema(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(compatibleSchema);
  if (!value || typeof value !== 'object') return value;
  const result: Record<string, unknown> = {};
  for (const [key, child] of Object.entries(value)) {
    if (['unevaluatedProperties', 'unevaluatedItems', 'prefixItems', 'maxContains', '$dynamicRef', '$dynamicAnchor', 'dependentSchemas', 'dependentRequired'].includes(key))
      throw new Error(`Unsupported schema assertion: ${key}`);
    if (key === 'minContains') {
      if (child !== 1 || !('contains' in value)) throw new Error('Unsupported minContains assertion');
      continue;
    }
    if (key !== '$schema' && key !== '$id') result[key] = compatibleSchema(child);
  }
  return result;
}
