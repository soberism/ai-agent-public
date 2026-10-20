const paths = {
  checklist: "M4 5h2M10 5h10M4 12h2M10 12h10M4 19h2M10 19h10",
  review: "M12 3a9 9 0 1 0 9 9h-9V3Zm3 0v6h6a9 9 0 0 0-6-6Z",
  pencil: "m4 15 11-11 5 5-11 11-6 1 1-6Zm9-9 5 5M4 15l5 5",
  search: "M19 10.5a7.5 7.5 0 1 1-15 0 7.5 7.5 0 0 1 15 0ZM17 16l4 5",
  family: "m3 10 9-7 9 7M5 9v12h14V9M9 21v-8h6v8",
  contacts: "M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM4 21v-2a8 8 0 0 1 16 0v2",
  document: "M14 3H5v18h14V8l-5-5Zm0 0v5h5M8 12h8M8 16h8",
  archive: "M3 3h18v18H3V3Zm6 0v18M12 8h6M12 12h6M12 16h6",
  approve: "m3 12 6 6L21 6",
  meal: "m12 3 9 9-9 9-9-9 9-9Z",
  medical: "M9 3h6v6h6v6h-6v6H9v-6H3V9h6V3Z",
  voice: "M15 6a3 3 0 0 0-6 0v6a3 3 0 0 0 6 0V6ZM5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8",
  chevron: "m9 5 7 7-7 7",
} as const;

export function FeatureIcon({ name }: { name: keyof typeof paths }) {
  return (
    <svg className="feature-icon" aria-hidden="true" viewBox="0 0 24 24">
      <path d={paths[name]} />
    </svg>
  );
}
