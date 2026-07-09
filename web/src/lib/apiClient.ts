// The Go server puts a per-launch bearer token in the URL fragment (see
// internal/server/token.go). We read it once on load, strip it from the
// visible URL, and attach it to every /api/v1 call. See REBUILD_PLAN.md §A2.

let launchToken = '';
let startupTenantHint = '';

export function initLaunchToken(): void {
  const params = new URLSearchParams(window.location.hash.slice(1));
  const token = params.get('token');
  if (token) {
    launchToken = token;
    startupTenantHint = params.get('tenant') ?? '';
    const url = new URL(window.location.href);
    url.hash = '';
    window.history.replaceState(null, '', url.toString());
  }
}

/** Tenant ID passed via `--tenant` on the CLI, if any. Read once at startup. */
export function getStartupTenantHint(): string {
  return startupTenantHint;
}

/** URL for EventSource, which cannot set headers so the token travels as a query param. */
export function eventsUrl(): string {
  return `/api/v1/events?token=${encodeURIComponent(launchToken)}`;
}

export class ApiError extends Error {
  code: string;
  roleHint?: string;

  constructor(code: string, message: string, roleHint?: string) {
    super(message);
    this.code = code;
    this.roleHint = roleHint;
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/v1${path}`, {
    ...init,
    headers: {
      ...init?.headers,
      Authorization: `Bearer ${launchToken}`,
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const err = body?.error;
    throw new ApiError(
      err?.code ?? 'unknown_error',
      err?.message ?? `Request to ${path} failed with ${res.status}`,
      err?.roleHint,
    );
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}
