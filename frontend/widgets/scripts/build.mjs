// Builds, for every clinic, the loader (dist/<id>.js) and the full widget (dist/<id>.app.js),
// then fails the build if any file is over its gzip size limit.
// --preview builds into dist-preview/ with the mock backend inside, for trying the widget on a real page
// before the backend is live. Nothing is saved in a preview; never put it on the public pages.
import { build } from 'vite';
import preact from '@preact/preset-vite';
import { rmSync } from 'node:fs';
import { resolve } from 'node:path';
import { CLINICS } from './clinics.mjs';
import { checkSizes } from './size.mjs';

const preview = process.argv.includes('--preview');
const outDir = preview ? 'dist-preview' : 'dist';
const root = resolve(import.meta.dirname, '..');
rmSync(resolve(root, outDir), { recursive: true, force: true });

async function bundle(entry, fileName) {
  await build({
    root,
    configFile: false,
    logLevel: 'warn',
    plugins: [preact()],
    define: { 'import.meta.env.VITE_PREVIEW': JSON.stringify(preview ? '1' : '0') },
    build: {
      outDir,
      emptyOutDir: false,
      target: 'es2019',
      lib: { entry: resolve(root, entry), formats: ['iife'], name: 'NeoWidget', fileName: () => fileName },
      // One file per clinic: the preview's mock is inlined instead of split into a chunk.
      rollupOptions: { output: { inlineDynamicImports: true } },
    },
  });
  console.log(`built ${outDir}/${fileName}`);
}

for (const clinic of CLINICS) {
  await bundle(`${clinic.dir}/main.ts`, `${clinic.id}.js`);
  await bundle(`${clinic.dir}/app.ts`, `${clinic.id}.app.js`);
}

// Size limits apply to the real widget files only.
if (!preview && !checkSizes()) process.exit(1);
