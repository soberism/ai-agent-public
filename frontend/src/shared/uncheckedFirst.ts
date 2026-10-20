export function uncheckedFirst<T>(items: readonly T[], checked: (item: T) => boolean): T[] {
  return [...items].sort((a, b) => Number(checked(a)) - Number(checked(b)));
}
