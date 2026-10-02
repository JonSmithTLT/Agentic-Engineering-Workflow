import { createRoot } from 'react-dom/client';
import { QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import type { ComponentType } from 'react';
import { Shell } from './components/Shell';
import { queryClient, installVisibility } from './client/queries';
import {
  DashboardProvider,
  PageSnapshot,
  useCapability,
} from './client/dashboard';
import { OverviewPage } from './pages/Overview';
import { WorkPage, WorkDetailPage } from './pages/Work';
import { Unavailable } from './components/States';
import './styles.css';
function NextStage({ name }: { name: string }) {
  const value = useCapability(name);
  return (
    <>
      <PageSnapshot />
      {!value.available ? (
        <Unavailable explanation={value.explanation} />
      ) : (
        <div className="empty">
          <h1>View in preparation</h1>
          <p>
            This view is scheduled after the Overview and Work visual
            review.
          </p>
          <Link to="/">Return to Overview</Link>
        </div>
      )}
    </>
  );
}
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
              {[
                'runs',
                'evidence',
                'knowledge',
                'history',
                'attention',
                'queue',
              ].flatMap((path) => [
                <Route
                  key={path}
                  path={path}
                  element={
                    <NextStage
                      name={
                        path === 'attention' ? 'action_projection' : path
                      }
                    />
                  }
                />,
                <Route
                  key={path + '-detail'}
                  path={path + '/:id'}
                  element={
                    <NextStage
                      name={
                        path === 'attention' ? 'action_projection' : path
                      }
                    />
                  }
                />,
              ])}
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
