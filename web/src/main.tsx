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
  const saved = localStorage.getItem('aew-theme');
  if (saved && ['system', 'light', 'dark'].includes(saved))
    document.documentElement.dataset.theme = saved;
  let DemoTools: ComponentType | undefined;
  if (import.meta.env.MODE === 'demo') {
    const { worker } = await import('./api/mock/browser');
    await worker.start({
      onUnhandledRequest: 'bypass',
      serviceWorker: { url: '/mockServiceWorker.js' },
    });
    DemoTools = (await import('./api/mock/DemoTools')).default;
  }
  installVisibility(queryClient);
  createRoot(document.getElementById('root')!).render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <DashboardProvider>
          <Routes>
            <Route
              element={
                <Shell demoTools={DemoTools ? <DemoTools /> : undefined} />
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
              <Route path="knowledge" element={<KnowledgePage />} />
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
