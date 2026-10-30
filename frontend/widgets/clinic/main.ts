// The one loader for every clinic (dist/clinic.js). The website includes:
//   <script src="<backend>/v1/widget/clinic.js" data-clinic="CL101" defer></script>
// The look comes from the clinic's published Appearance; until then these default colours are used.
import { boot, loadScript } from '../core/loader';
import themeCss from '../neo-follicle/theme.css?inline';

const tag = document.currentScript as HTMLScriptElement | null;
const clinicId = tag?.dataset.clinic || (tag?.src ? new URL(tag.src).searchParams.get('clinic') : null) || '';

if (/^CL\d{2,3}$/.test(clinicId)) {
  boot({
    clinicId,
    themeCss,
    loadApp: (handle) => (import.meta.env.DEV ? import('./app') : loadScript(handle.appUrl)),
  });
} else {
  console.warn('[neo-widget] add the clinic code to the script line, e.g. data-clinic="CL101"');
}
