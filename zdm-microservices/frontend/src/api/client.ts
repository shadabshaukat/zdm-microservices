export type ApiSettings = {
  apiBase: string;
  username: string;
  password: string;
};

export type ApiError = Error & {
  detail?: unknown;
};

export type HealthResponse = {
  status: 'ok';
};

export function loadApiSettings(): ApiSettings {
  return {
    apiBase: sessionStorage.getItem('zeus.apiBase') || '',
    username: sessionStorage.getItem('zeus.username') || '',
    password: sessionStorage.getItem('zeus.password') || '',
  };
}

export function saveApiSettings(settings: ApiSettings) {
  sessionStorage.setItem('zeus.apiBase', settings.apiBase.replace(/\/$/, ''));
  sessionStorage.setItem('zeus.username', settings.username);
  sessionStorage.setItem('zeus.password', settings.password);
}

export async function apiFetch(
  settings: ApiSettings,
  path: string,
  init: RequestInit = {},
): Promise<unknown> {
  const base = settings.apiBase || '';
  const auth = btoa(`${settings.username}:${settings.password}`);
  const response = await fetch(`${base}${path}`, {
    ...init,
    headers: {
      Authorization: `Basic ${auth}`,
      'Content-Type': 'application/json',
      ...(init.headers || {}),
    },
  });
  const text = await response.text();
  const payload = parseJsonPayload(text);
  if (!response.ok) {
    const error = new Error(
      backendErrorMessage(response.status, payload, text),
    ) as ApiError;
    error.detail = payload;
    throw error;
  }
  return payload;
}

function parseJsonPayload(text: string): unknown {
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return {};
  }
}

function backendErrorMessage(status: number, payload: unknown, text: string) {
  const detail = apiErrorDetail(payload);
  if (detail) return `ZEUS backend error (HTTP ${status}): ${detail}`;
  const fallback = text.trim();
  if (fallback) return `ZEUS backend error (HTTP ${status}): ${fallback.slice(0, 240)}`;
  return `ZEUS backend could not complete the request (HTTP ${status}).`;
}

function apiErrorDetail(payload: unknown): string {
  if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) return '';
  const detail = (payload as Record<string, unknown>).detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === 'string') return item;
        if (typeof item === 'object' && item !== null && 'msg' in item) {
          const msg = (item as Record<string, unknown>).msg;
          return typeof msg === 'string' ? msg : '';
        }
        return '';
      })
      .filter(Boolean)
      .join('; ');
  }
  if (typeof detail === 'object' && detail !== null) return JSON.stringify(detail);
  return '';
}

export function validateHealthResponse(payload: unknown): HealthResponse {
  const isObject = typeof payload === 'object' && payload !== null && !Array.isArray(payload);
  if (
    !isObject
    || Object.keys(payload as Record<string, unknown>).join('|') !== 'status'
    || (payload as Record<string, unknown>).status !== 'ok'
  ) {
    throw new Error('GET /health API contract error: expected { status: "ok" }.');
  }
  return payload as HealthResponse;
}
