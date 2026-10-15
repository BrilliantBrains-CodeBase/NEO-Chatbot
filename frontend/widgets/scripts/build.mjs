// Builds, for every clinic, the loader (dist/<id>.js) and the full widget (dist/<id>.app.js),
// then fails the build if any file is over its gzip size limit.
import { build } from 'vite';
import preact from '@preact/preset-vite';
import { rmSync } from 'node:fs';
import { resolve } from 'node:path';
import { CLINICS } from './clinics.mjs';
import { checkSizes } from './size.mjs';

const root = resolve(import.meta.dirname, '..');
rmSync(resolve(root, 'dist'), { recursive: true, force: true });

async function bundle(entry, fileName) {
  await build({
    root,
    configFile: false,
    logLevel: 'warn',
    plugins: [preact()],
    build: {
      outDir: 'dist',
      emptyOutDir: false,
      target: 'es2019',
      lib: { entry: resolve(root, entry), formats: ['iife'], name: 'NeoWidget', fileName: () => fileName },
    },
  });
  console.log(`built dist/${fileName}`);
}

for (const clinic of CLINICS) {
  await bundle(`${clinic.dir}/main.ts`, `${clinic.id}.js`);
  await bundle(`${clinic.dir}/app.ts`, `${clinic.id}.app.js`);
}

if (!checkSizes()) process.exit(1);
