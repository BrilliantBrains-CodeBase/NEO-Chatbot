// Builds dist/neo-fertility.js, dist/neo-follicle.js and dist/derma-solutions.js,
// then fails the build if any bundle is over the gzip size limit.
import { build } from 'vite';
import preact from '@preact/preset-vite';
import { rmSync } from 'node:fs';
import { resolve } from 'node:path';
import { CLINICS } from './clinics.mjs';
import { checkSizes } from './size.mjs';

const root = resolve(import.meta.dirname, '..');
rmSync(resolve(root, 'dist'), { recursive: true, force: true });

for (const clinic of CLINICS) {
  await build({
    root,
    configFile: false,
    logLevel: 'warn',
    plugins: [preact()],
    build: {
      outDir: 'dist',
      emptyOutDir: false,
      target: 'es2019',
      cssCodeSplit: false,
      lib: {
        entry: resolve(root, clinic.entry),
        formats: ['iife'],
        name: 'NeoWidget',
        fileName: () => `${clinic.id}.js`,
      },
    },
  });
  console.log(`built dist/${clinic.id}.js`);
}

if (!checkSizes()) process.exit(1);
