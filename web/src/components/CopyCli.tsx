import { useState } from 'react';
import { readOnlyCommand, readOnlyHistoryArgv } from '../api/cli';
export function CopyCli({ kind, id, argv }: { kind: string; id: string; argv?: readonly string[] }) {
  const command = argv ? readOnlyHistoryArgv(argv) : readOnlyCommand(kind, id);
  const [message, setMessage] = useState('');
  if (!command) return null;
  return (
    <span className="copy-cli">
      <button
        title={command}
        aria-label={`Copy read-only CLI for ${id}`}
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(command);
            setMessage('Copied');
          } catch {
            setMessage('Clipboard unavailable. Select the command below.');
          }
        }}
      >
        Copy CLI
      </button>
      {message && (
        <span role="status">
          {message}
          {message !== 'Copied' && <code tabIndex={0}>{command}</code>}
        </span>
      )}
    </span>
  );
}
