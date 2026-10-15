// Prints the raw and gzip size of every built file and returns false if any is over its limit.
import { readFileSync, existsSync } from 'node:fs';
import { gzipSync } from 'node:zlib';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { CLINICS, MAX_LOADER_GZIP_KB, MAX_APP_GZIP_KB } from './clinics.mjs';

const dist = resolve(import.meta.dirname, '..', 'dist');

export function checkSizes() {
  let ok = true;
  const files = CLINICS.flatMap(({ id }) => [
    [`${id}.js`, MAX_LOADER_GZIP_KB],
    [`${id}.app.js`, MAX_APP_GZIP_KB],
  ]);
  for (const [name, limit] of files) {
    const file = resolve(dist, name);
    if (!existsSync(file)) {
      console.error(`missing dist/${name}, run npm run build first`);
      ok = false;
      continue;
    }
    const raw = readFileSync(file);
    const gz = gzipSync(raw).length / 1024;
    const over = gz > limit;
    if (over) ok = false;
    console.log(
      `${over ? 'FAIL' : 'ok  '} ${name.padEnd(24)} ${(raw.length / 1024).toFixed(1)} KB raw, ${gz.toFixed(1)} KB gzip (limit ${limit} KB)`,
    );
  }
  return ok;
}

if (import.meta.url === pathToFileURL(process.argv[1]).href && !checkSizes()) process.exit(1);
