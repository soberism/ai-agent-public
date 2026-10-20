export function Avatar({
  id,
  name,
  nickname,
  email,
}: {
  id: string;
  name?: string;
  nickname?: string | null;
  email: string;
}) {
  const label = Array.from((name || nickname || email).trim())[0]?.toUpperCase() ?? "?";
  const tone = (id.codePointAt(id.length - 1) ?? 0) % 6;

  return (
    <span className={`avatar avatar-tone-${tone}`} aria-hidden="true">
      {label}
    </span>
  );
}
