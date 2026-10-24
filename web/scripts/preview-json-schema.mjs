import { z } from 'zod';

// Preserve the registered preview artifacts' plain nullable-string representation.
// This changes serialization only; runtime schemas and canonical digests stay fixed.
export function previewJSONSchema(schema) {
  function preserve(value) {
    if (Array.isArray(value)) return value.map(preserve);
    if (value === null || typeof value !== 'object') return value;
    if (Object.keys(value).length === 1 && Array.isArray(value.type) &&
        value.type.length === 2 && value.type[0] === 'string' && value.type[1] === 'null') {
      return { anyOf: [{ type: 'string' }, { type: 'null' }] };
    }
    return Object.fromEntries(Object.entries(value).map(([key, child]) => [key, preserve(child)]));
  }
  return preserve(z.toJSONSchema(schema));
}
