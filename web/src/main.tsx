import { createRoot } from 'react-dom/client';
import { QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import type { ComponentType } from 'react';
import { Shell } from './components/Shell';
import { queryClient, installVisibility } from './client/queries';
import { DashboardProvider } from './client/dashboard';
import { OverviewPage } from './pages/Overview';
import { WorkPage, WorkDetailPage } from './pages/Work';
import {
  RunsPage,
  RunDetailPage,
  EvidencePage,
  EvidenceDetailPage,
  KnowledgePage,
  KnowledgeDetailPage,
} from './pages/Records';
import { HistoryPage, HistoryDetailPage } from './pages/History';
import { AttentionPage, QueuePage } from './pages/Attention';
import './styles.css';
async function start() {
  let saved: string | null = null;
  try {
    saved = localStorage.getItem('aew-theme');
  } catch {
    /* Storage is optional. */
  }
  if (saved && ['system', 'light', 'dark'].includes(saved))
    document.documentElement.dataset.theme = saved;
  let DemoTools: ComponentType | undefined;
  let DemoLab: ComponentType<{ tab: string }> | undefined;
  let DemoKnowledge: ComponentType<{ Records: ComponentType }> | undefined;
  if (import.meta.env.MODE === 'demo') {
    const { httpDemo, initializeDemo } = await import('./api/mock/runtime');
    await initializeDemo();
    if (!httpDemo) {
    const { worker } = await import('./api/mock/browser');
    await worker.start({
      onUnhandledRequest: 'bypass',
      serviceWorker: {
        url: '/mockServiceWorker.js',
        options: { updateViaCache: 'none' },
      },
    });
    }
    DemoTools = (await import('./api/mock/DemoTools')).default;
    DemoLab = (await import('./api/mock/lab/Lab')).default;
    DemoKnowledge = (await import('./api/preview/journal/Journal')).default;
  }
  let detachVisibility = installVisibility(queryClient);
  // Stop old-document reads when navigation actually hides the page.
  // Resume focus/revision handling when restored from the browser back cache.
  window.addEventListener(
    'pagehide',
    () => {
      detachVisibility();
      void queryClient.cancelQueries();
    },
    { capture: true },
  );
  window.addEventListener('pageshow', (event) => {
    if (event.persisted) {
      detachVisibility = installVisibility(queryClient);
      void queryClient.refetchQueries({ type: 'active' });
    }
  });
  createRoot(document.getElementById('root')!).render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <DashboardProvider>
          <Routes>
            <Route
              element={
                <Shell
                  demoTools={DemoTools ? <DemoTools /> : undefined}
                  demoLab={DemoLab}
                />
              }
            >
              <Route index element={<OverviewPage />} />
              <Route path="overview" element={<OverviewPage />} />
              <Route path="work" element={<WorkPage />} />
              <Route path="work/:id" element={<WorkDetailPage />} />
              <Route path="runs" element={<RunsPage />} />
              <Route path="runs/:id" element={<RunDetailPage />} />
              <Route path="evidence" element={<EvidencePage />} />
              <Route path="evidence/:id" element={<EvidenceDetailPage />} />
              <Route path="knowledge" element={DemoKnowledge ? <DemoKnowledge Records={KnowledgePage} /> : <KnowledgePage />} />
              <Route path="knowledge/:id" element={<KnowledgeDetailPage />} />
              <Route path="history" element={<HistoryPage />} />
              <Route path="history/:id" element={<HistoryDetailPage />} />
              <Route path="attention" element={<AttentionPage />} />
              <Route path="queue" element={<QueuePage />} />
              <Route
                path="*"
                element={
                  <div className="empty">
                    <h1>Page not found</h1>
                    <Link to="/">Return to Overview</Link>
                  </div>
                }
              />
            </Route>
          </Routes>
        </DashboardProvider>
      </BrowserRouter>
    </QueryClientProvider>,
  );
}
void start();
