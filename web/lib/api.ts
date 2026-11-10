export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function parseError(response: Response): Promise<ApiError> {
  let code = "INTERNAL_ERROR";
  let message = `请求失败（${response.status}）`;
  try {
    const body = await response.json();
    if (body?.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
    }
  } catch {
    // ignore invalid error body
  }
  return new ApiError(response.status, code, message);
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData) && init.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  if (
    response.status === 401 &&
    !path.startsWith("/auth/") &&
    typeof window !== "undefined"
  ) {
    window.dispatchEvent(new Event("auth:unauthorized"));
  }
  if (!response.ok) {
    throw await parseError(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function apiUpload<T>(
  path: string,
  formData: FormData,
  method = "POST",
): Promise<T> {
  return apiFetch<T>(path, { method, body: formData });
}
