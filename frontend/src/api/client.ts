import { env } from "@/lib/env";

export type ApiError = {
  status: number;
  code: string;
  message: string;
};

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const requestId = crypto.randomUUID();
  const response = await fetch(`${env.VITE_API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "X-Request-ID": requestId,
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let payload: { error?: { code?: string; message?: string } } = {};
    try {
      payload = (await response.json()) as typeof payload;
    } catch {
      // body wasn't JSON; fall through with empty payload
    }
    const err: ApiError = {
      status: response.status,
      code: payload.error?.code ?? "unknown",
      message: payload.error?.message ?? response.statusText,
    };
    throw err;
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
