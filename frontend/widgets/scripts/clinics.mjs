// One entry per clinic. Clinic 4 is added here with its own face folder.
// Each clinic builds two files:
//   <id>.js      the loader the website includes (launcher only)
//   <id>.app.js  the full widget, fetched by the loader on first open
export const CLINICS = [
  { id: 'neo-fertility', dir: 'neo-fertility' },
  { id: 'neo-follicle', dir: 'neo-follicle' },
  { id: 'derma-solutions', dir: 'derma-solutions' },
];

// Compressed (gzip) size limits, from the README targets.
export const MAX_LOADER_GZIP_KB = 5;
export const MAX_APP_GZIP_KB = 40;
