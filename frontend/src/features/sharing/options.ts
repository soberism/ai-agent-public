import type { SharingHousehold } from "./types";

type Options = { households: SharingHousehold[] };
let cached: { owner: string; generation: number; expires: number; value: Options } | null = null;

export async function sharingOptions(
  owner: string,
  generation: number,
  fetchOptions: () => Promise<Options>,
): Promise<Options> {
  if (cached?.owner === owner && cached.generation === generation && cached.expires > Date.now())
    return cached.value;
  const value = await fetchOptions();
  cached = { owner, generation, expires: Date.now() + 60000, value };
  return value;
}

export function invalidateSharingOptions() {
  cached = null;
}
