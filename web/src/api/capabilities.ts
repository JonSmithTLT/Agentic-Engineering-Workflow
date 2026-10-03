export type CapabilityView = {
  available: boolean;
  state: string;
  explanation: string;
};
export function capabilityView(value?: {
  state: string;
  reasons: { code: string; message: string | null }[];
}): CapabilityView {
  const state = value?.state ?? 'UNKNOWN';
  const known = ['AVAILABLE', 'UNAVAILABLE', 'UNSUPPORTED', 'UNKNOWN'].includes(
    state,
  );
  return {
    available: state === 'AVAILABLE',
    state,
    explanation:
      value?.reasons
        .map((r) => `${r.code}${r.message ? `: ${r.message}` : ''}`)
        .join('; ') ||
      (known
        ? `Capability ${state.toLowerCase()}`
        : `Unknown capability state: ${state}`),
  };
}
