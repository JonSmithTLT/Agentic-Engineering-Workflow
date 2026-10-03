import { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { dashboardCopyLink } from '../api/navigation';
export function CopyDashboardLink() {
  const location = useLocation(),
    [fallback, setFallback] = useState(''),
    [message, setMessage] = useState('');
  return (
    <span className="copy-dashboard">
      <button
        onClick={async () => {
          const value = dashboardCopyLink(
            location.pathname,
            location.search,
            window.location.origin,
          );
          try {
            await navigator.clipboard.writeText(value);
            setFallback('');
            setMessage('Dashboard link copied.');
          } catch {
            setFallback(value);
            setMessage('Clipboard unavailable. Select and copy this link.');
          }
        }}
      >
        Copy dashboard link
      </button>
      {message && <span role="status">{message}</span>}
      {fallback && (
        <input
          aria-label="Dashboard link"
          readOnly
          value={fallback}
          onFocus={(e) => e.currentTarget.select()}
        />
      )}
    </span>
  );
}
