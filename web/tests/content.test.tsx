import { render } from '@testing-library/react';
import { expect, it } from 'vitest';
import { SafeContent, JsonContent } from '../src/components/Content';
import {
  CapabilityWarnings,
  SemanticValue,
} from '../src/components/States';
import { capabilityView } from '../src/api/capabilities';
import { entityLink } from '../src/api/links';
import world from '../src/api/mock/fixtures/F8.json';
it('hostile Markdown has no scripts, raw HTML, remote images or dangerous links', () => {
  const body = world.responses['/evidence'].data.items[0].body;
  const { container } = render(<SafeContent {...body} />);
  expect(container.querySelector('script,img,iframe')).toBeNull();
  expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
  expect(container.querySelector('pre code')?.textContent).toContain(
    '<script>alert(1)</script>',
  );
});
it('escapes JSON and marks external navigation explicitly', () => {
  const { container } = render(
    <>
      <JsonContent value={{ html: '<script>bad()</script>' }} />
      <SafeContent
        format="markdown"
        text="[reference](https://example.com)"
      />
    </>,
  );
  expect(container.querySelector('script')).toBeNull();
  const a = container.querySelector('a');
  expect(a?.rel).toBe('noopener noreferrer');
  expect(a?.textContent).toContain('(external)');
});
it('unknown semantic values and absent capabilities stay explicit', () => {
  const { getByText } = render(
    <SemanticValue value="FUTURE_STATE" known={['CURRENT']} />,
  );
  expect(getByText('FUTURE_STATE')).toBeTruthy();
  for (const state of ['UNAVAILABLE', 'UNSUPPORTED', 'UNKNOWN', 'FUTURE'])
    expect(capabilityView({ state, reasons: [] }).available).toBe(false);
  expect(capabilityView().state).toBe('UNKNOWN');
  expect(
    capabilityView({ state: 'AVAILABLE', reasons: [] }).available,
  ).toBe(true);
});
it('opaque identities are encoded and unknown entity kinds do not invent routes', () => {
  expect(entityLink({ kind: 'ticket', id: 'space /%:#?' })).toBe(
    '/work/space%20%2F%25%3A%23%3F',
  );
  expect(entityLink({ kind: 'future', id: 'x' })).toBeUndefined();
});

it('shows unknown capability names and states without losing available projections', () => {
  const { getByText } = render(
    <CapabilityWarnings
      values={{
        future_projection: {
          state: 'AVAILABLE',
          reasons: [
            { code: 'future', message: 'Backend feature explanation' },
          ],
        },
        activity: { state: 'FUTURE_CAPABILITY', reasons: [] },
      }}
    />,
  );
  expect(getByText('future_projection')).toBeTruthy();
  expect(getByText('Backend feature explanation')).toBeTruthy();
  expect(getByText('FUTURE_CAPABILITY')).toBeTruthy();
  expect(entityLink({ kind: 'invocation', id: 'INV-0001' })).toBe(
    '/runs/INV-0001',
  );
  expect(
    entityLink({ kind: 'harness_run', id: 'R-INV-0001-1' }),
  ).toBeUndefined();
});
