import type { SharingPolicy } from "./types";

type States = { states: Record<string, SharingPolicy["scope"]>; editable: string[] };
type Pending = {
  load: (keys: string[]) => Promise<States>;
  requests: {
    key: string;
    resolve: (scope: SharingPolicy["scope"] | undefined) => void;
    reject: (reason: unknown) => void;
  }[];
};
const pending = new Map<string, Pending>();
const known = new Map<string, SharingPolicy["scope"]>();

export function knownVisibilityState(owner: string, key: string) {
  return known.get(`${owner}:${key}`) ?? null;
}

export function rememberVisibilityState(
  owner: string,
  key: string,
  scope?: SharingPolicy["scope"],
) {
  const cacheKey = `${owner}:${key}`;
  if (scope) known.set(cacheKey, scope);
  else known.delete(cacheKey);
}

export function visibilityState(owner: string, key: string, load: Pending["load"]) {
  return new Promise<SharingPolicy["scope"] | undefined>((resolve, reject) => {
    const group = pending.get(owner);
    if (group) {
      group.requests.push({ key, resolve, reject });
      return;
    }
    const next: Pending = { load, requests: [{ key, resolve, reject }] };
    pending.set(owner, next);
    queueMicrotask(async () => {
      pending.delete(owner);
      try {
        const keys = [...new Set(next.requests.map((request) => request.key))];
        // Batch at the API limit; each visible group normally fits one request.
        for (let index = 0; index < keys.length; index += 200) {
          const part = keys.slice(index, index + 200);
          const result = await next.load(part);
          for (const request of next.requests.filter((request) => part.includes(request.key))) {
            const scope = result.editable?.includes(request.key)
              ? result.states?.[request.key]
              : undefined;
            rememberVisibilityState(owner, request.key, scope);
            request.resolve(scope);
          }
        }
      } catch (error) {
        next.requests.forEach((request) => request.reject(error));
      }
    });
  });
}
