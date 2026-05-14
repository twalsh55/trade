export const TRADE_SESSION_COOKIE = "trade_session_token";

export function sanitizeRedirectTo(value: string | null | undefined): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) {
    return "/";
  }
  return value;
}
