// Mock backend: answers like the real FastAPI backend will, using the contract in core/types.ts.
// Used by the dev playground and the Playwright tests only; it is never part of a clinic's widget file.
// The full Arya flows (frontend.md) are added in piece 8.
import type { ChatRequest, ChatResponse } from '../core/types';

const GREETING: Record<string, string> = {
  CL01: "Hi, I'm Arya, Neo Follicle's AI assistant. How can I help you today?",
  CL02: "Hi, I'm Navya, Neo Fertility's AI assistant. How can I help you today?",
  CL03: "Hi, I'm Diya, Derma Solutions' AI assistant. How can I help you today?",
};

const NO_ANSWER =
  "I don't have a confirmed answer for that yet. Share your number and our team will call you back with the right information.";

export function handle(req: ChatRequest): ChatResponse {
  if (req.event === 'text') {
    return {
      messages: [{ type: 'text', text: NO_ANSWER }],
      input: { mode: 'text', placeholder: 'Type your question' },
    };
  }
  const greeting = GREETING[req.client_id] ?? 'Hi, how can I help you today?';
  return {
    messages: [{ type: 'text', text: greeting }],
    input: { mode: 'text', placeholder: 'Type your question' },
  };
}
