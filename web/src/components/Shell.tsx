import { useState, type ReactNode } from 'react';
import { useDashboard } from '../client/dashboard';
import { SemanticValue, CapabilityWarnings } from './States';
import { NavLink, Outlet } from 'react-router-dom';
const navigation = [
  ['/', 'Overview'],
  ['/attention', 'Attention'],
  ['/work', 'Work'],
  ['/runs', 'Runs'],
  ['/evidence', 'Evidence'],
  ['/knowledge', 'Knowledge'],
  ['/history', 'History / integrity'],
  ['/queue', 'Queue'],
];
export function Shell({ demoTools }: { demoTools?: ReactNode }) {
  const { project, overview, caps } = useDashboard();
  const demo = import.meta.env.MODE === 'demo';
  const [open, setOpen] = useState(false);
  const [theme, setTheme] = useState(
    () => localStorage.getItem('aew-theme') ?? 'system',
  );
  function changeTheme(value: string) {
    setTheme(value);
    document.documentElement.dataset.theme = value;
    localStorage.setItem('aew-theme', value);
  }
  const search = demo ? window.location.search : '';
  return (
    <div className="workbench">
      <a className="skip-link" href="#content">
        Skip to content
      </a>
      <aside className={open ? 'sidebar open' : 'sidebar'}>
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            a
          </span>
          <div>
            <strong>AEW</strong>
            <small>Engineering workbench</small>
          </div>
        </div>
        <nav aria-label="Main navigation">
          {navigation.map(([path, label]) => (
            <NavLink
              key={path}
              end={path === '/'}
              to={path + search}
              onClick={() => setOpen(false)}
            >
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <span className="read-only">Read-only inspection</span>
          <p>Workflow authority remains with AEW.</p>
          <label>
            Appearance
            <select
              aria-label="Appearance"
              value={theme}
              onChange={(e) => changeTheme(e.target.value)}
            >
              <option value="system">System</option>
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </select>
          </label>
        </div>
      </aside>
      <div className="workspace">
        <header className="project-header">
          <button
            className="nav-toggle"
            onClick={() => setOpen(!open)}
            aria-expanded={open}
            aria-label="Toggle navigation"
          >
            ☰
          </button>
          <div>
            <strong>
              {project.data?.value.data.name ?? 'AEW dashboard'}
            </strong>
            <small>
              {project.data?.value.project_id ?? 'Waiting for project'}
            </small>
          </div>
          <div className="header-tools">
            {overview.data && caps?.overview?.state === 'AVAILABLE' && (
              <SemanticValue
                value={overview.data.value.data.health.status}
                known={['HEALTHY', 'DEGRADED', 'UNHEALTHY', 'UNKNOWN']}
              />
            )}
            {demoTools}
            <span className="header-status">
              {demo ? 'Demo data' : 'Read-only'}
            </span>
          </div>
        </header>
        <main id="content" tabIndex={-1}>
          {caps && <CapabilityWarnings values={caps} />}
          <Outlet />
        </main>
        <footer>
          AEW workbench <span>Accepted API 0.1.2 · Overview and Work</span>
        </footer>
      </div>
    </div>
  );
}
