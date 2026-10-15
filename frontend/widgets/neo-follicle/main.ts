// Loader for this clinic (dist/neo-follicle.js). The website includes only this file.
import { boot, loadScript } from '../core/loader';
import themeCss from './theme.css?inline';

boot({
  clinicId: 'neo-follicle',
  themeCss,
  loadApp: (handle) => (import.meta.env.DEV ? import('./app') : loadScript(handle.appUrl)),
});
