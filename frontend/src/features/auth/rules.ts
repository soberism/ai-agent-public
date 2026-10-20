export function safeReturnTo(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\"))
    return "/";
  try {
    const target = new URL(value, window.location.origin);
    if (
      target.origin !== window.location.origin ||
      target.pathname === "/login" ||
      target.pathname === "/register"
    )
      return "/";
    return `${target.pathname}${target.search}${target.hash}`;
  } catch {
    return "/";
  }
}
