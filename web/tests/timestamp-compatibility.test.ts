import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import { timestamp } from '../src/api/schema';
import artifact from '../docs/design/journal-preview-0.1.0.json';

describe('frozen UTC timestamp compatibility', () => {
  it('exports the exact frozen timestamp schema', () => {
    expect(z.toJSONSchema(timestamp)).toEqual({
      $schema: 'https://json-schema.org/draft/2020-12/schema',
      ...artifact.schemas.JournalResponse.properties.generated_at,
    });
  });
  it.each(['2026-10-24T12:34Z', '2026-10-24T12:34:56Z', '2024-02-29T23:59:59.123Z'])(
    'preserves accepted UTC representation %s', (value) => {
      expect(timestamp.parse(value)).toBe(value);
    },
  );
  it.each(['2026-02-29T12:00Z', '2026-10-24T24:00Z', '2026-10-24T12:34:60Z', '2026-10-24T12:34+00:00', '2026-10-24T12:34'])(
    'rejects values outside the frozen grammar: %s', (value) => {
      expect(timestamp.safeParse(value).success).toBe(false);
    },
  );
});
