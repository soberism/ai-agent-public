export class ApiError extends Error {
  status: number;
  code: string;
  fields: Record<string, string>;
  retryAfter: number;
  constructor(status: number, code: string, message: string, fields = {}, retryAfter = 0) {
    super(message);
    this.status = status;
    this.code = code;
    this.fields = fields;
    this.retryAfter = retryAfter;
  }
}
export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(
    () => controller.abort(),
    path === "/assistant/transcriptions" || path.endsWith("/transcribe") ? 45000 : 15000,
  );
  const abort = () => controller.abort();
  options.signal?.addEventListener("abort", abort, { once: true });
  try {
    const write = options.method && options.method !== "GET";
    const response = await fetch(`/api${path}`, {
      ...options,
      credentials: "same-origin",
      cache: "no-store",
      signal: controller.signal,
      headers: {
        ...(write ? { "X-App-Request": "1" } : {}),
        ...(write && !(options.body instanceof FormData)
          ? { "Content-Type": "application/json" }
          : {}),
        ...options.headers,
      },
    });
    if (response.status === 204) return undefined as T;
    const body = await response.json().catch(() => null);
    if (!response.ok)
      throw new ApiError(
        response.status,
        body?.error?.code ?? "UNKNOWN_ERROR",
        body?.error?.message ?? "服务暂时不可用，请重试",
        body?.error?.fields,
        Number(response.headers.get("Retry-After")) || 0,
      );
    if (body === null) throw new ApiError(0, "UNKNOWN_RESULT", "响应无法确认，请重试核对");
    return body as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(0, "NETWORK_ERROR", "连接中断或请求超时，请检查网络后重试");
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener("abort", abort);
  }
}
export const messageOf = (error: unknown) =>
  error instanceof Error ? error.message : "操作失败，请重试";
