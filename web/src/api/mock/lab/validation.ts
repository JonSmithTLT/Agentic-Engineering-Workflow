import { acceptedContract } from '../../registry';
import * as vocabulary from '../../vocabulary';
const known: Record<string, readonly string[]> = {
  WorkResponse: vocabulary.workStates,
  WorkListResponse: vocabulary.workStates,
  InvocationResponse: vocabulary.invocationStatuses,
  InvocationListResponse: vocabulary.invocationStatuses,
};
export function validateInput(model: string, text: string) {
  if (new TextEncoder().encode(text).length > 256 * 1024)
    return { status: 'Input exceeds 256 KiB', issues: [] };
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    return { status: 'Invalid JSON', issues: [] };
  }
  const schema = acceptedContract.parsers[model];
  if (!schema)
    return { status: 'Unknown registered response schema', issues: [] };
  const parsed = schema.safeParse(value);
  if (!parsed.success)
    return {
      status: 'Invalid shape',
      issues: parsed.error.issues
        .slice(0, 100)
        .map((issue) => ({
          field: issue.path.map(String).join('.') || '$',
          message: issue.message.slice(0, 512),
        })),
    };
  const envelope = parsed.data as { data?: unknown };
  const data = envelope.data as
    | {
        items?: { state?: string; status?: string }[];
        state?: string;
        status?: string;
      }
    | undefined;
  const items = data?.items ?? (data ? [data] : []);
  const warnings = known[model]
    ? items.flatMap((item, i) => {
        const field = model.startsWith('Work') ? 'state' : 'status',
          raw = item[field];
        return raw && !known[model].includes(raw)
          ? [
              {
                field: data?.items
                  ? `data.items.${i}.${field}`
                  : `data.${field}`,
                message: `Unknown semantic value: ${raw.slice(0, 512)}`,
              },
            ]
          : [];
      })
    : [];
  return {
    status: warnings.length
      ? 'Accepted shape; unknown semantic values'
      : 'Accepted shape',
    issues: warnings.slice(0, 100),
  };
}
