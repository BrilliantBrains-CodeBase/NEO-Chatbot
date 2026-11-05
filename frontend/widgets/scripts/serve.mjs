// Tiny static server for tests: serves dist/ (the built widget files) and tests/fixtures/ (sample clinic pages).
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { resolve, extname, normalize } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const dirs = [resolve(root, 'dist'), resolve(root, 'tests', 'fixtures')];
const types = {
  '.js': 'text/javascript',
  '.html': 'text/html',
  '.css': 'text/css',
  '.json': 'application/json',
};
const port = Number(process.env.PORT || 4173);

// The two questions the built widget asks before it shows: may it show here, and with what look.
const answers = (pathname) => {
  if (pathname === '/v1/widget/show') return { show: true, capture: false };
  if (pathname.startsWith('/v1/widget/config/')) return { appearance: null, template: null };
  return null;
};

createServer(async (req, res) => {
  const pathname = new URL(req.url, 'http://x').pathname;
  const answer = answers(pathname);
  if (answer) {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    return res.end(JSON.stringify(answer));
  }
  const path = normalize(decodeURIComponent(pathname)).replace(/^([/\\])+/, '');
  for (const dir of dirs) {
    const file = resolve(dir, path || 'index.html');
    if (!file.startsWith(dir)) break;
    try {
      const body = await readFile(file);
      res.writeHead(200, { 'Content-Type': types[extname(file)] || 'application/octet-stream' });
      return res.end(body);
    } catch {
      // try the next folder
    }
  }
  res.writeHead(404).end('not found');
}).listen(port, () => console.log(`serving dist and fixtures on http://localhost:${port}`));
