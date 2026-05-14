export const BRIVOLY_SESSION_COOKIE = "brivoly_session_token";
export const LEGACY_TRADE_SESSION_COOKIE = "trade_session_token";

export function sanitizeRedirectTo(value: string | null | undefined): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) {
    return "/";
  }
  return value;
}
