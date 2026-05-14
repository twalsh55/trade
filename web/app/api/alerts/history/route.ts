import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { getAlertHistory } from "@/lib/api";
import { BRIVOLY_SESSION_COOKIE, LEGACY_TRADE_SESSION_COOKIE } from "@/lib/auth";

export async function GET(request: Request) {
  const cookieStore = await cookies();
  const sessionToken =
    cookieStore.get(BRIVOLY_SESSION_COOKIE)?.value ?? cookieStore.get(LEGACY_TRADE_SESSION_COOKIE)?.value ?? null;
  if (!sessionToken) {
    return NextResponse.json({ error: "Authentication required." }, { status: 401 });
  }

  const url = new URL(request.url);
  const limit = Number(url.searchParams.get("limit") ?? "20");

  try {
    const alerts = await getAlertHistory({ sessionToken });
    return NextResponse.json({
      items: alerts.items.slice(0, Number.isFinite(limit) ? limit : 20),
      count: Math.min(alerts.count, Number.isFinite(limit) ? limit : 20),
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to load alert history.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
