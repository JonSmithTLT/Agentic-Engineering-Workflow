import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import { responseSchemas } from '../src/api/schema';
import { WorkInvocations } from '../src/components/WorkInvocations';
import f1 from '../src/api/mock/fixtures/F1.json';

const state = vi.hoisted(() => ({ overview: undefined as unknown, available: true }));
vi.mock('../src/client/dashboard', () => ({
  useDashboard: () => ({ overview: state.overview }),
  useCapability: () => ({ available: state.available }),
}));
const work = responseSchemas.WorkResponse.parse(f1.responses['/work/T-0001']).data;
const overview = responseSchemas.OverviewResponse.parse(f1.responses['/overview']);
beforeEach(() => {
  state.available = true;
  state.overview = { data: { value: structuredClone(overview) }, isError: false };
});
function mount(record = work, project = overview.project_id) {
  return render(<MemoryRouter><WorkInvocations record={record} project={project} /></MemoryRouter>);
}
it('matches exact supplied work identity and kind, deduplicates references, and preserves roles/status', () => {
  const data = structuredClone(overview);
  const matching = data.data.runs[0];
  matching.work = { kind: 'work', id: work.id, title: work.title };
  matching.role = 'NEW_ROLE';
  matching.status = 'NEW_STATUS';
  data.data.runs = [matching, { ...matching, id: 'Wrong-kind', work: { ...matching.work, kind: 'evidence' } }, { ...matching, id: 'Wrong-work', work: { ...matching.work, id: 'T-other' } }];
  state.overview = { data: { value: data }, isError: false };
  mount({ ...work, related: [{ kind: 'invocation', id: matching.id, title: null }, { kind: 'invocation', id: 'Historical-invocation', title: 'Earlier review attempt' }] });
  expect(screen.getAllByRole('link', { name: matching.id })).toHaveLength(1);
  expect(screen.getByText('NEW_ROLE').closest('[role="status"]')?.textContent).toBe('Unknown value: NEW_ROLE');
  expect(screen.getByText('NEW_STATUS').closest('[role="status"]')?.textContent).toBe('Unknown value: NEW_STATUS');
  expect(screen.queryByText('Wrong-kind')).toBeNull();
  expect(screen.queryByText('Wrong-work')).toBeNull();
  expect(screen.getByRole('link', { name: 'Historical-invocation' }).getAttribute('href')).toBe('/runs/Historical-invocation');
  expect(screen.getByText('Earlier review attempt')).toBeTruthy();
  expect(screen.getByText(/not a complete invocation history/)).toBeTruthy();
});
it('does not associate another project summary with the work', () => {
  mount({ ...work, related: [] }, 'Other-project');
  expect(screen.queryByRole('list')).toBeNull();
  expect(screen.getByText(/Other invocations may exist/)).toBeTruthy();
});
it('withdraws unavailable overview data while preserving supplied Work references', () => {
  state.available = false;
  mount({ ...work, related: [{ kind: 'invocation', id: 'Supplied-only', title: null }] });
  const list = screen.getByRole('list');
  expect(within(list).getAllByRole('listitem')).toHaveLength(1);
  expect(screen.queryByText(/Overview revision/)).toBeNull();
  expect(screen.queryByRole('link')).toBeNull();
});
it('marks ordinary refresh failure and removes refused summary content', () => {
  state.overview = { data: { value: overview }, isError: true };
  const view = mount();
  expect(screen.getByRole('status').textContent).toContain('last-known-good');
  state.overview = { data: undefined, isError: true };
  view.rerender(<MemoryRouter><WorkInvocations record={{ ...work, related: [] }} project={overview.project_id} /></MemoryRouter>);
  expect(screen.queryByRole('list')).toBeNull();
  expect(screen.queryByText(/Overview revision/)).toBeNull();
});
