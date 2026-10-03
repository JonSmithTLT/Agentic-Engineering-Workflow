import { transport } from '../src/api/transport';
import { setReadClock } from '../src/client/clock';
import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
afterEach(() => {
  cleanup();
  transport.reset();
  setReadClock();
  vi.restoreAllMocks();
  vi.useRealTimers();
});
