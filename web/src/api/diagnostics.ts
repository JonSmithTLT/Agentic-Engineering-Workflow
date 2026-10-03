export type RequestTrace = {
  id: number;
  path: string;
  context?: string;
  started_at: string;
  duration_ms: number;
  status: number | null;
  request_etag?: string;
  response_etag?: string;
  represented_etag?: string;
  control_revision?: string;
  project_id?: string;
  validation: { field: string; code: string; message: string }[];
  error?: string;
  diagnostic?: string;
};
export class RequestLog {
  private entries: readonly RequestTrace[] = [];
  private listeners = new Set<() => void>();
  private sequence = 0;
  constructor(private limit = 200) {}
  snapshot = () => this.entries;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  record(trace: Omit<RequestTrace, 'id'>) {
    this.entries = [{ ...trace, id: ++this.sequence }, ...this.entries].slice(
      0,
      this.limit,
    );
    for (const listener of this.listeners) listener();
  }
  clear = () => {
    this.entries = [];
    for (const listener of this.listeners) listener();
  };
}
export const requestLog = new RequestLog();
