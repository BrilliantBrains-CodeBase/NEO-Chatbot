// Line icons from the approved mockups (24 x 24, stroke).
const PATHS: Record<string, string> = {
  cal: 'M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2zM8 3v4M16 3v4M3 10h18',
  search: 'M10.5 4a6.5 6.5 0 1 1 0 13 6.5 6.5 0 0 1 0-13zM15.5 15.5L20 20M10.5 8v5M8 10.5h5',
  steth: 'M6 3v6a4 4 0 0 0 8 0V3M10 13v3a4 4 0 0 0 8 0v-2M18 10a2 2 0 1 1 0 4 2 2 0 0 1 0-4z',
  globe: 'M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18zM3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18',
  phone: 'M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2',
  chat: 'M4 5h16v11H9l-5 4z',
  sos: 'M12 3l9 16H3zM12 10v4M12 17v.5',
  send: 'M4 12l16-8-6 16-2.5-6.5z',
  close: 'M6 6l12 12M18 6L6 18',
  restart: 'M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5',
  back: 'M15 6l-6 6 6 6',
  next: 'M9 6l6 6-6 6',
  menu: 'M4 7h16M4 12h16M4 17h16',
};

export function Icon({ name }: { name: string }) {
  const d = PATHS[name];
  if (!d) return null;
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}
