import { id as identity } from './schema';
// IDs are URL-safe opaque identities. This stricter allowlist also makes them
// single, non-option shell arguments in both POSIX shells and PowerShell.
export function readOnlyCommand(kind: string, id: string): string | undefined {
  if (!identity.safeParse(id).success) return;
  const commands: Record<string, string> = {
    work: 'work show',
    epic: 'work show',
    story: 'work show',
    ticket: 'work show',
    invocation: 'invoke show',
    history: 'history show',
    audit: 'history show',
  };
  return Object.hasOwn(commands, kind)
    ? `aew ${commands[kind]} ${id}`
    : undefined;
}
/** Supplied search argv is accepted only as the documented history-show template. */
export function readOnlyHistoryArgv(argv: readonly string[]): string | undefined {
  if (argv.length !== 4 || argv[0] !== 'aew' || argv[1] !== 'history' || argv[2] !== 'show') return;
  return readOnlyCommand('history', argv[3]);
}
