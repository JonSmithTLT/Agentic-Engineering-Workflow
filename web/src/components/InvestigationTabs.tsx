export function InvestigationTabs({ label, tabs, active, select, prefix }: { label: string; tabs: { id: string; label: string }[]; active: string; select: (id: string) => void; prefix: string }) {
  return <div className="journal-tabs" role="tablist" aria-label={label}>{tabs.map((tab, index) => <button key={tab.id} id={`${prefix}-tab-${tab.id}`} role="tab" aria-selected={active === tab.id} aria-controls={`${prefix}-panel-${tab.id}`} tabIndex={active === tab.id ? 0 : -1} onClick={() => select(tab.id)} onKeyDown={event => {
    const next = event.key === 'ArrowRight' ? (index + 1) % tabs.length : event.key === 'ArrowLeft' ? (index + tabs.length - 1) % tabs.length : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : -1;
    if (next >= 0) { event.preventDefault(); select(tabs[next].id); document.getElementById(`${prefix}-tab-${tabs[next].id}`)?.focus(); }
  }}>{tab.label}</button>)}</div>;
}
export function focusBelowHeader(element: HTMLElement | null) {
  if (!element) return;
  element.focus({ preventScroll: true });
  const bottom = document.querySelector('.project-header')?.getBoundingClientRect().bottom ?? 0;
  const top = element.getBoundingClientRect().top;
  if (top < bottom + 12 || top > window.innerHeight - 80) window.scrollBy({ top: top - bottom - 16, behavior: 'instant' });
}
