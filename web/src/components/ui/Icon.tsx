// Icon paths copied from plan/template/assets/app.js (iconPaths) so the navigation looks identical.
const PATHS = {
  overview: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  inbox: "M4 4h16v16H4z M4 13h5l2 3h2l2-3h5",
  diallists: "M8 6h13 M8 12h13 M8 18h13 M3 6h1 M3 12h1 M3 18h1",
  calls: "M7 3l3 5-3 3c2 3 3 4 6 6l3-3 5 3c-1 5-4 5-8 3C7 17 3 12 3 7c0-2 1-4 4-4z",
  customers:
    "M16 21v-3a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v3 M9 10a4 4 0 1 0 0-8 4 4 0 0 0 0 8 M17 3a4 4 0 0 1 0 7 M22 21v-3a4 4 0 0 0-3-4",
  tasks: "M4 5h16v16H4z M8 2v6 M16 2v6 M4 10h16 M8 14h3",
  agents: "M5 7h14v13H5z M9 12h.1 M15 12h.1 M9 16h6 M12 3v4 M2 11v5 M22 11v5",
  knowledge: "M5 3h10l4 4v14H5z M14 3v5h5 M8 12h8 M8 16h6",
  campaigns: "M4 14V8l14-5v16L4 14z M7 15l2 6h3l-2-5 M21 8v6",
  integrations: "M8 4v4 M16 4v4 M5 8h14v3a7 7 0 0 1-14 0z M12 18v4",
  sip: "M5 5h14v5H5z M5 14h14v5H5z M8 7h.1 M8 16h.1 M12 10v4",
  reports: "M4 20V10 M10 20V4 M16 20v-8 M22 20H2",
  billing: "M3 5h18v14H3z M3 10h18 M7 15h4",
  settings:
    "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M12 2v3 M12 19v3 M2 12h3 M19 12h3 M5 5l2 2 M17 17l2 2 M5 19l2-2 M17 7l2-2",
  handoff: "M3 7h15l-4-4 M18 7l-4 4 M21 17H6l4-4 M6 17l4 4",
  automations: "M13 2L4 14h7l-1 8 10-13h-7z",
  // not in the template: voice spike (M0.5) reuses a waveform-like glyph
  spike: "M3 12h2 M7 8v8 M11 5v14 M15 9v6 M19 11v2 M21 12h0",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name }: { name: IconName }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.65"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
