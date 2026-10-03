import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { dashboardEntityLink } from '../api/navigation';
import { id as identity } from '../api/schema';
import { useCapability } from '../client/dashboard';
const kinds = {
  work: 'Work (Epic / Story / Ticket)',
  invocation: 'Run / invocation',
  evidence: 'Evidence',
  history: 'History',
  knowledge: 'Knowledge',
};
const caps = {
  work: 'work',
  invocation: 'runs',
  evidence: 'evidence',
  history: 'history',
  knowledge: 'knowledge',
};
export function JumpToId() {
  const [open, setOpen] = useState(false),
    [id, setId] = useState(''),
    [kind, setKind] = useState<keyof typeof kinds>('work'),
    [error, setError] = useState('');
  const dialog = useRef<HTMLDialogElement>(null),
    input = useRef<HTMLInputElement>(null),
    trigger = useRef<HTMLButtonElement>(null);
  const navigate = useNavigate(),
    location = useLocation(),
    capability = useCapability(caps[kind]);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen(true);
      }
    };
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  }, []);
  useEffect(() => {
    if (open) {
      dialog.current?.showModal();
      input.current?.focus();
    } else if (dialog.current?.open) {
      dialog.current.close();
      trigger.current?.focus();
    }
  }, [open]);
  return (
    <>
      <button ref={trigger} onClick={() => setOpen(true)} title="Ctrl/Cmd + K">
        Jump to ID
      </button>
      <dialog
        className="jump-dialog"
        ref={dialog}
        aria-labelledby="jump-heading"
        onCancel={() => setOpen(false)}
      >
        <h2 id="jump-heading">Jump to an ID</h2>
        <p>
          IDs are opaque. Choose the projection to inspect; no search or
          existence check is performed.
        </p>
        <form
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            const value = id.trim();
            if (!identity.safeParse(value).success) {
              setError('Enter a URL-safe AEW record ID.');
              return;
            }
            if (!capability.available) {
              setError(capability.explanation);
              return;
            }
            navigate(
              dashboardEntityLink({ kind, id: value }, location.search)!,
            );
            setError('');
            setOpen(false);
          }}
        >
          <label>
            Record type
            <select
              aria-label="Jump record type"
              value={kind}
              onChange={(e) => setKind(e.target.value as keyof typeof kinds)}
            >
              {Object.entries(kinds).map(([k, label]) => (
                <option key={k} value={k}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Record ID
            <input
              ref={input}
              aria-label="Jump record ID"
              value={id}
              onChange={(e) => {
                setId(e.target.value);
                setError('');
              }}
              autoComplete="off"
              maxLength={512}
            />
          </label>
          {error && <p role="alert">{error}</p>}
          <div className="dialog-actions">
            <button type="submit">Open record</button>
            <button type="button" onClick={() => setOpen(false)}>
              Cancel
            </button>
          </div>
        </form>
      </dialog>
    </>
  );
}
