import type { ChatRequest, ChatResponse } from './types';

export type ApiErrorKind = 'offline' | 'timeout' | 'server' | 'client' | 'bad_response';

export class ApiError extends Error {
  constructor(
    public kind: ApiErrorKind,
    message: string,
  ) {
    super(message);
  }
}

export interface ApiOptions {
  timeoutMs?: number;
  retries?: number;
  // Swapped for the mock backend in development and tests (Step 8).
  fetchImpl?: typeof fetch;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function createApi(apiBase: string, opts: ApiOptions = {}) {
  const { timeoutMs = 10000, retries = 2, fetchImpl = fetch.bind(window) } = opts;

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    let lastError: ApiError = new ApiError('server', 'Request failed');
    for (let attempt = 0; attempt <= retries; attempt++) {
      if (attempt) await sleep(500 * 2 ** (attempt - 1));
      if (!navigator.onLine) throw new ApiError('offline', 'Browser is offline');

      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), timeoutMs);
      try {
        const res = await fetchImpl(apiBase + path, {
          ...init,
          signal: ctrl.signal,
          headers: { 'Content-Type': 'application/json', ...init.headers },
        });
        if (res.ok) {
          try {
            return (await res.json()) as T;
          } catch {
            throw new ApiError('bad_response', 'Response is not valid JSON');
          }
        }
        // 4xx (except rate limit) will not succeed on retry.
        if (res.status < 500 && res.status !== 429) throw new ApiError('client', `HTTP ${res.status}`);
        lastError = new ApiError('server', `HTTP ${res.status}`);
      } catch (err) {
        if (err instanceof ApiError && err.kind !== 'server') throw err;
        lastError =
          err instanceof ApiError
            ? err
            : ctrl.signal.aborted
              ? new ApiError('timeout', 'Request timed out')
              : new ApiError('offline', 'Network error');
      } finally {
        clearTimeout(timer);
      }
    }
    throw lastError;
  }

  return {
    send: (body: ChatRequest) =>
      request<ChatResponse>('/v1/chat/message', { method: 'POST', body: JSON.stringify(body) }),
  };
}

export type Api = ReturnType<typeof createApi>;
