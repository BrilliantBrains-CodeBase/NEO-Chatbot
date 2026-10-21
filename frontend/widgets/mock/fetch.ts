// fetch() replacement for the dev playground: routes the widget's API calls to the mock backend.
import type { ChatRequest } from '../core/types';
import { handle } from './engine';

const LATENCY_MS = 400;

export async function mockFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const path = new URL(String(input), location.href).pathname;
  await new Promise((r) => setTimeout(r, LATENCY_MS));
  if (path === '/v1/chat/message' && init?.method === 'POST') {
    const req = JSON.parse(String(init.body)) as ChatRequest;
    return Response.json(handle(req));
  }
  return Response.json({ detail: 'Not Found' }, { status: 404 });
}
