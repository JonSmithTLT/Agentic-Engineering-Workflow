import { createRoot } from 'react-dom/client';
import { QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import type { ComponentType } from 'react';
import { Shell } from './components/Shell';
import { queryClient, installVisibility } from './client/queries';
import './styles.css';
function Pending() {
  return (
    <div className="empty">
      <h1>AEW dashboard foundation</h1>
      <p>
        The read-only workbench is awaiting C0 contract review and backend
        integration.
      </p>
      <p>Domain views will be enabled against the reviewed contract.</p>
    </div>
  );
}
async function start() {
  const saved = localStorage.getItem('aew-theme');
  if (saved && ['system', 'light', 'dark'].includes(saved))
    document.documentElement.dataset.theme = saved;
  let Overview: ComponentType = Pending;
  let Ticket: ComponentType = Pending;
  if (import.meta.env.MODE === 'demo') {
    const { worker } = await import('./api/mock/browser');
    await worker.start({
      onUnhandledRequest: 'bypass',
      serviceWorker: { url: '/mockServiceWorker.js' },
    });
    const preview = await import('./api/mock/Preview');
    Overview = preview.OverviewPreview;
    Ticket = preview.TicketPreview;
  }
  installVisibility(queryClient);
  createRoot(document.getElementById('root')!).render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<Shell />}>
            <Route index element={<Overview />} />
            <Route path="work/:id" element={<Ticket />} />
            <Route path="*" element={<Pending />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>,
  );
}
void start();
