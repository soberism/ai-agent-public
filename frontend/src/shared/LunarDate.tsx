import { lunarLabel } from "./lunar";

export function lunarTileContent({ date, view }: { date: Date; view: string }) {
  if (view !== "month") return null;
  const label = lunarLabel(date);
  return (
    <span className="calendar-lunar" aria-label={`农历${label}`}>
      {label}
    </span>
  );
}
