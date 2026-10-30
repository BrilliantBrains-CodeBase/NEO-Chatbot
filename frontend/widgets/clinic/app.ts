// Full widget for the shared loader (dist/clinic.app.js): mounts every clinic the loader started on this page
// that has not mounted yet. The bot's name comes from the clinic's published Appearance.
import { mountApp } from '../core/app';

for (const handle of Object.values(window.__neoWidgets ?? {})) {
  if (!handle.onOpenChange) {
    mountApp({ clinicId: handle.clinicId, botName: handle.appearance?.look.name || 'Assistant' });
  }
}
