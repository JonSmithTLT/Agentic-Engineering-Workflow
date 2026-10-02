import { useState } from 'react';
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
export function Shell() {
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
            <strong>Agentic Engineering Workflow</strong>
            <small>Local dashboard</small>
          </div>
          <span className="header-status">
            {demo ? 'Demo data' : 'Awaiting integration'}
          </span>
        </header>
        <main id="content" tabIndex={-1}>
          <Outlet />
        </main>
        <footer>
          AEW workbench{' '}
          <span>
            {demo
              ? 'Provisional design preview • C0 review pending'
              : 'Frontend foundation • C0 review pending'}
          </span>
        </footer>
      </div>
    </div>
  );
}
