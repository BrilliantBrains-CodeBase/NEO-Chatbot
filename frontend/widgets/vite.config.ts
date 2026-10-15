import { defineConfig } from 'vite';
import preact from '@preact/preset-vite';

// Dev server only. Production bundles are built one clinic at a time by scripts/build.mjs,
// because each clinic site loads a single self-contained IIFE file from a plain <script> tag.
export default defineConfig({
  plugins: [preact()],
  server: { port: 5173, open: '/playground/' },
});
