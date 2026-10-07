import { act, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { deferredScreen } from '../src/api/mock/DeferredScreen';

it('keeps surrounding controls available while a requested screen loads, and preserves props', async () => {
  let finish!: (value: { default: (props: { id: string }) => React.ReactNode }) => void;
  const load = vi.fn(() => new Promise<{ default: (props: { id: string }) => React.ReactNode }>(resolve => { finish = resolve; }));
  const Screen = deferredScreen('Investigation', load);
  expect(load).not.toHaveBeenCalled();
  const view = render(<><button>API panel</button><Screen id="first" /></>);
  expect(screen.getByRole('status').textContent).toBe('Opening Investigation…');
  expect(screen.getByRole('button', { name: 'API panel' })).toBeTruthy();
  await act(async () => { finish({ default: ({ id }) => <h1>{id}</h1> }); });
  expect(screen.getByRole('heading').textContent).toBe('first');
  view.rerender(<><button>API panel</button><Screen id="second" /></>);
  expect(screen.getByRole('heading').textContent).toBe('second');
  expect(load).toHaveBeenCalledTimes(1);
});

it('contains a failed screen and offers reload without exposing the failure payload', async () => {
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
  try {
    const Screen = deferredScreen<object>('Investigation', () => Promise.reject(new Error('private failure payload')));
    render(<><button>API panel</button><Screen /></>);
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('Investigation could not open');
    expect(alert.textContent).not.toContain('private failure payload');
    expect(screen.getByRole('button', { name: 'Reload page' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'API panel' })).toBeTruthy();
  } finally {
    consoleError.mockRestore();
  }
});
