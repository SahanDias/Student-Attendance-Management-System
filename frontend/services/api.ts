/**
 * Core HTTP client for the FastAPI attendance backend.
 *
 * Flip USE_MOCK to false (or set NEXT_PUBLIC_USE_MOCK=false) to talk to the
 * real backend. Domain-specific calls live in the sibling *.service.ts
 * files; this module only owns the fetch wrapper, base-URL configuration
 * and error handling shared by all of them.
 */
import { authHeaders } from "./auth.service";

export const USE_MOCK = process.env["NEXT_PUBLIC_USE_MOCK"] !== "false";

const DEFAULT_BASE = process.env["NEXT_PUBLIC_API_URL"] ?? "http://localhost:8000/api";

// Removed now that the Settings page no longer lets an operator override the
// API base per-browser -- only cleanup of a value saved by that old field
// remains, so a browser that saved one doesn't keep silently pointing at it.
const STALE_BASE_KEY = "sams.api_base";

const STATIC_BASE = (
  process.env["NEXT_PUBLIC_STATIC_URL"] ?? "http://127.0.0.1:8000/static"
).replace(/\/+$/, "");

export function getApiBase(): string {
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(STALE_BASE_KEY);
  }
  return DEFAULT_BASE;
}

/**
 * Backend paths are stored relative to the storage root, e.g.
 * "storage/steps/{id}/01_resize.png" -- but the /static mount already serves
 * that root directly, so the leading "storage/" segment must be stripped or
 * the request 404s looking for storage/storage/... on disk. The static base
 * comes from its own env var rather than being derived from the API URL,
 * since the two don't share a path prefix to strip in a general way.
 */
export function staticUrl(path: string): string {
  if (!path) return "";
  if (path.startsWith("data:") || path.startsWith("http")) return path;
  const relative = path.replace(/^\/+/, "").replace(/^storage\//, "");
  return `${STATIC_BASE}/${relative}`;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${getApiBase()}${path}`, {
    ...init,
    headers: { ...authHeaders(), ...init?.headers },
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export const delay = (ms: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, ms));

export async function pingBackend(): Promise<{ ok: boolean; latency_ms: number; message: string }> {
  const started = Date.now();
  if (USE_MOCK) {
    await delay(420);
    return { ok: true, latency_ms: Date.now() - started, message: "Mock backend responding" };
  }
  try {
    const apiBase = getApiBase().replace(/\/?api\/?$/, "");
    const res = await fetch(`${apiBase}/health`);
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return { ok: true, latency_ms: Date.now() - started, message: "Connected" };
  } catch (e) {
    return { ok: false, latency_ms: Date.now() - started, message: (e as Error).message };
  }
}
