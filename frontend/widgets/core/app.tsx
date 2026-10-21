// Entry for the full widget (<id>.app.js). Picks up the handle the loader created and renders into it.
import { render } from 'preact';
import { useCallback, useEffect, useState } from 'preact/hooks';
import baseCss from './styles/base.css?inline';
import { injectStyles } from './shadow';
import { getHandle, type WidgetHandle } from './registry';
import { createApi } from './api';
import { getVisitorId, getSession } from './session';
import { Panel } from './components/Panel';

export interface Face {
  clinicId: string;
  botName: string;
}

function Widget({ handle, face }: { handle: WidgetHandle; face: Face }) {
  const [open, setOpen] = useState(handle.isOpen);
  const close = useCallback(() => handle.setOpen(false), [handle]);

  useEffect(() => {
    handle.onOpenChange = setOpen;
    return () => {
      handle.onOpenChange = undefined;
    };
  }, [handle]);

  // The widget stays mounted while closed, so the conversation is kept when the patient reopens it.
  if (!open) return null;
  return <Panel botName={face.botName} onClose={close} />;
}

export function mountApp(face: Face) {
  const handle = getHandle(face.clinicId);
  if (!handle) {
    console.warn(`[neo-widget] loader for ${face.clinicId} not found`);
    return;
  }
  injectStyles(handle.shadow, baseCss);
  // Created here so later steps can use them; nothing is sent until Step 5.
  createApi(handle.apiBase, face.clinicId);
  getVisitorId();
  getSession(face.clinicId);
  render(<Widget handle={handle} face={face} />, handle.mountPoint);
}
