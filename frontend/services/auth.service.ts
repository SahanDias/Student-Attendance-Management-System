/**
 * This application has no login flow — the FastAPI backend exposes no
 * auth endpoints today. This module exists so a token, once the backend
 * grows one, has a single place to be stored and attached to requests
 * without another restructure of the service layer. Until then every
 * function here is a harmless no-op path: `authHeaders()` returns `{}`.
 */
const TOKEN_KEY = "sams.auth_token";

export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setAuthToken(token: string): void {
  if (typeof window !== "undefined") window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearAuthToken(): void {
  if (typeof window !== "undefined") window.localStorage.removeItem(TOKEN_KEY);
}

export function authHeaders(): Record<string, string> {
  const token = getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
