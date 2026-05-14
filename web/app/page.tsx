import { cookies } from "next/headers";

import { AppShell } from "@/components/app-shell";
import { TRADE_SESSION_COOKIE } from "@/lib/auth";
import { getShellData } from "@/lib/api";

export default async function HomePage() {
  const cookieStore = await cookies();
  const tradeSessionToken = cookieStore.get(TRADE_SESSION_COOKIE)?.value ?? null;
  const sessionCookie = cookieStore.get("__session")?.value;
  const cookieHeader = sessionCookie ? `__session=${sessionCookie}` : null;
  const data = await getShellData({ sessionToken: tradeSessionToken, cookieHeader });

  return <AppShell data={data} />;
}
