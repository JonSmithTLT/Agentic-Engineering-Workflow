import { expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { Shell } from '../src/components/Shell';
vi.mock('../src/client/dashboard', () => ({ useDashboard: () => ({ project: { data: { value: { project_id: 'synthetic-settings', data: { name: 'Synthetic project' } } } }, overview: {}, caps: {} }), useCapability: () => ({ available: false, state: 'UNSUPPORTED', reasons: [] }) }));
vi.mock('../src/client/queries', () => ({ useReadSession: () => ({ generation: 1, identity: { snapshot: 'live' } }) }));
function SelectedRoute() { const location = useLocation(); return <p>Selected route: {location.pathname}{location.search}</p>; }
it('closes the shared navigation without changing selection and restores header-trigger focus', () => {
  render(<MemoryRouter initialEntries={['/settings?settings_profile=0']}><Routes><Route element={<Shell />}><Route path="settings" element={<SelectedRoute />} /></Route></Routes></MemoryRouter>);
  const trigger = screen.getByRole('button', { name: 'Toggle navigation' });
  expect(trigger.getAttribute('aria-controls')).toBe('main-sidebar');
  fireEvent.click(trigger);
  expect(trigger.getAttribute('aria-expanded')).toBe('true');
  fireEvent.click(screen.getByRole('button', { name: 'Close navigation' }));
  expect(trigger.getAttribute('aria-expanded')).toBe('false');
  expect(document.activeElement).toBe(trigger);
  expect(screen.getByText('Selected route: /settings?settings_profile=0')).toBeDefined();
});
