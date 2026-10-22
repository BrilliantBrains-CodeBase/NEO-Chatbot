import { defineConfig } from 'vite';
import preact from '@preact/preset-vite';

// Dev server only. Production bundles are built one clinic at a time by scripts/build.mjs,
// because each clinic site loads a single self-contained IIFE file from a plain <script> tag.
export default defineConfig({
  plugins: [preact()],
  // 127.0.0.1, not localhost: on this PC localhost resolves to IPv6 only, so 127.0.0.1 was refused.
  server: { host: '127.0.0.1', port: 5173, strictPort: true, open: '/playground/?clinic=neo-follicle' },
});
