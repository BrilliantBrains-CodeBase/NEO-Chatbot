// Prints the raw and gzip size of each clinic bundle and returns false if any is over the limit.
import { readFileSync, existsSync } from 'node:fs';
import { gzipSync } from 'node:zlib';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { CLINICS, MAX_GZIP_KB } from './clinics.mjs';

const dist = resolve(import.meta.dirname, '..', 'dist');

export function checkSizes() {
  let ok = true;
  for (const { id } of CLINICS) {
    const file = resolve(dist, `${id}.js`);
    if (!existsSync(file)) {
      console.error(`missing dist/${id}.js, run npm run build first`);
      ok = false;
      continue;
    }
    const raw = readFileSync(file);
    const gz = gzipSync(raw).length / 1024;
    const over = gz > MAX_GZIP_KB;
    if (over) ok = false;
    console.log(
      `${over ? 'FAIL' : 'ok  '} ${id}.js  ${(raw.length / 1024).toFixed(1)} KB raw, ${gz.toFixed(1)} KB gzip (limit ${MAX_GZIP_KB} KB)`,
    );
  }
  return ok;
}

if (import.meta.url === pathToFileURL(process.argv[1]).href && !checkSizes()) process.exit(1);
