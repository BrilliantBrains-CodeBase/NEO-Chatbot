import { render } from 'preact';

export interface FaceOptions {
  clinicId: string;
  botName: string;
}

// Step 1 placeholder: proves the build pipeline per clinic.
// Step 2 replaces this with the Shadow DOM shell, launcher and panel.
export function mount({ clinicId, botName }: FaceOptions) {
  const host = document.createElement('div');
  host.id = `neo-widget-${clinicId}`;
  document.body.appendChild(host);
  render(<div data-clinic={clinicId}>{botName}</div>, host);
}
