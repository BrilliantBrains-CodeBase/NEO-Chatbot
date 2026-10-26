// The chat's icon set, grouped for the icon picker (Dashboard → Menu buttons). Copied from the approved
// Dashboard design; each is plain SVG shapes (path, rect, circle, line) drawn on a 24 × 24 grid.
export const ICON_GROUPS: [string, string[]][] = [
  [
    "Care",
    [
      "stetho",
      "heart",
      "tooth",
      "baby",
      "drop",
      "pill",
      "syringe",
      "eye",
      "hospital",
      "ambulance",
      "doctor",
      "scissors",
      "leaf",
    ],
  ],
  ["Booking", ["calendar", "calcheck", "clock", "form", "list"]],
  [
    "Contact",
    [
      "phone",
      "whatsapp",
      "chat",
      "mail",
      "headset",
      "pin",
      "map",
      "car",
      "globe",
    ],
  ],
  [
    "Information",
    [
      "search",
      "info",
      "question",
      "star",
      "award",
      "gift",
      "rupee",
      "file",
      "download",
      "video",
      "image",
      "spark",
      "thumb",
      "lang",
      "home",
      "tiles",
      "alert",
      "shield",
    ],
  ],
  ["Social", ["instagram", "youtube", "facebook"]],
];

export const CHAT_ICONS: Record<string, string> = {
  pill: '<rect x="2.5" y="8.5" width="19" height="7" rx="3.5" transform="rotate(-45 12 12)"/><path d="M9.5 9.5l5 5"/>',
  stetho:
    '<path d="M6 3v6a4 4 0 0 0 8 0V3"/><path d="M10 13v2a5 5 0 0 0 10 0v-2"/><circle cx="20" cy="11" r="2"/>',
  heart:
    '<path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/>',
  tooth:
    '<path d="M7 3C4.5 3 3 5 3 7.5c0 3 1.5 4.5 2 7.5s1 6 2.5 6 1.5-4 2.5-6c.5-1 1.5-1 2 0 1 2 1 6 2.5 6s2-3 2.5-6 2-4.5 2-7.5C21 5 19.5 3 17 3c-2 0-3 1-5 1S9 3 7 3z"/>',
  baby: '<circle cx="12" cy="8" r="5"/><path d="M10 8h.01M14 8h.01M10.5 10.5a2 2 0 0 0 3 0"/><path d="M8 21v-3a4 4 0 0 1 8 0v3"/>',
  drop: '<path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z"/>',
  syringe:
    '<path d="M17 3l4 4M19 5l-3 3M15 5l4 4-9 9H6v-4z"/><path d="M6 18l-3 3M10 10l2 2M12 8l2 2"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  hospital:
    '<rect x="4" y="3" width="16" height="18" rx="1"/><path d="M12 7v6M9 10h6M9 21v-4h6v4"/>',
  ambulance:
    '<path d="M3 7h11v9H3zM14 10h4l3 3v3h-7"/><circle cx="7" cy="17.5" r="1.8"/><circle cx="17" cy="17.5" r="1.8"/><path d="M8.5 9.5v4M6.5 11.5h4"/>',
  doctor:
    '<circle cx="12" cy="7" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/><path d="M12 15v4M10 17h4"/>',
  scissors:
    '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M8.5 7.5L20 19M8.5 16.5L20 5"/>',
  leaf: '<path d="M5 19c0-9 6-14 15-14 0 9-5 15-14 15"/><path d="M5 19l8-8"/>',
  calendar:
    '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
  calcheck:
    '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4M9 15l2 2 4-4"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  form: '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6M9 12h6M9 16h3"/>',
  list: '<path d="M9 6h12M9 12h12M9 18h12M4 6h.01M4 12h.01M4 18h.01"/>',
  phone:
    '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2"/>',
  whatsapp:
    '<path d="M3.5 20.5l1.2-4.3A8.5 8.5 0 1 1 8 19.3z"/><path d="M9 9.2c0 3.1 2.6 5.8 5.8 5.8l1-1.5-2-1-.9.8a4 4 0 0 1-1.9-1.9l.8-.9-1-2z"/>',
  chat: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
  headset:
    '<path d="M4 14v-2a8 8 0 0 1 16 0v2"/><rect x="3" y="14" width="4" height="6" rx="1"/><rect x="17" y="14" width="4" height="6" rx="1"/><path d="M19 20a3 3 0 0 1-3 2h-3"/>',
  pin: '<path d="M12 21s-7-6-7-11a7 7 0 0 1 14 0c0 5-7 11-7 11z"/><circle cx="12" cy="10" r="2.5"/>',
  map: '<path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2z"/><path d="M9 4v14M15 6v14"/>',
  car: '<path d="M5 16h14v-4l-2-5H7l-2 5z"/><path d="M5 12h14"/><circle cx="8" cy="16.5" r="1.5"/><circle cx="16" cy="16.5" r="1.5"/>',
  globe:
    '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  question:
    '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 0 1 4.9.8c0 1.7-2.4 2.2-2.4 3.7M12 17h.01"/>',
  star: '<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/>',
  award: '<circle cx="12" cy="9" r="6"/><path d="M8.5 14L7 21l5-3 5 3-1.5-7"/>',
  gift: '<rect x="3" y="8" width="18" height="4" rx="1"/><path d="M5 12v9h14v-9M12 8v13M12 8c-4 0-6-4-3.5-4.5S12 8 12 8zm0 0c4 0 6-4 3.5-4.5S12 8 12 8z"/>',
  rupee: '<path d="M7 4h10M7 8h10M7 4h3a4 4 0 0 1 0 8H7l8 8"/>',
  file: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 13h6M9 17h4"/>',
  download: '<path d="M12 4v12M7 11l5 5 5-5M4 20h16"/>',
  video:
    '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="M16 10l5-3v10l-5-3"/>',
  image:
    '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5-9 9"/>',
  spark:
    '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 15.5l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z"/>',
  thumb:
    '<path d="M7 11v10H4V11zM7 11l4-8a2 2 0 0 1 2 2v4h6a2 2 0 0 1 2 2.3l-1.4 7A2 2 0 0 1 17.6 21H7"/>',
  lang: '<path d="M4 5h9M8.5 3v2M6 5c0 4 3 7 6 8M11 5c0 4-3 7-7 8"/><path d="M13 21l4-9 4 9M14.5 18h5"/>',
  home: '<path d="M3 11l9-8 9 8M5 9v12h14V9"/>',
  tiles:
    '<rect x="3" y="4" width="5" height="5" rx="1"/><rect x="9.5" y="4" width="5" height="5" rx="1"/><rect x="16" y="4" width="5" height="5" rx="1"/><rect x="3" y="14" width="18" height="6" rx="1"/>',
  alert: '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18h.01"/>',
  shield:
    '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
  instagram:
    '<rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><path d="M17.5 6.5h.01"/>',
  youtube:
    '<rect x="2" y="5" width="20" height="14" rx="4"/><path d="M10 9l5 3-5 3z"/>',
  facebook: '<path d="M14 8h3V4h-3a4 4 0 0 0-4 4v3H7v4h3v6h4v-6h3l1-4h-4V8z"/>',
};
