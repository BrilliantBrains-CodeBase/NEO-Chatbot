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

createServer(async (req, res) => {
  const path = normalize(decodeURIComponent(new URL(req.url, 'http://x').pathname)).replace(/^([/\\])+/, '');
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
