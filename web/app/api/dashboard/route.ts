import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { getDashboard } from "@/lib/api";
import { BRIVOLY_SESSION_COOKIE, LEGACY_TRADE_SESSION_COOKIE } from "@/lib/auth";

export async function GET(request: Request) {
  const cookieStore = await cookies();
  const sessionToken =
    cookieStore.get(BRIVOLY_SESSION_COOKIE)?.value ?? cookieStore.get(LEGACY_TRADE_SESSION_COOKIE)?.value ?? null;
  if (!sessionToken) {
    return NextResponse.json({ error: "Authentication required." }, { status: 401 });
  }

  const url = new URL(request.url);
  const universe = url.searchParams.getAll("universe").filter(Boolean);
  const benchmark = url.searchParams.get("benchmark") ?? undefined;
  const vix_symbol = url.searchParams.get("vix_symbol") ?? undefined;
  const risk_proxy = url.searchParams.get("risk_proxy") ?? undefined;
  const short_yield_symbol = url.searchParams.get("short_yield_symbol") ?? undefined;
  const long_yield_symbol = url.searchParams.get("long_yield_symbol") ?? undefined;
  const lookback_years = url.searchParams.get("lookback_years");

  try {
    const dashboard = await getDashboard({
      sessionToken,
      filters: {
        universe: universe.length ? universe : undefined,
        benchmark,
        vix_symbol,
        risk_proxy,
        short_yield_symbol,
        long_yield_symbol,
        lookback_years: lookback_years ? Number(lookback_years) : undefined,
      },
    });
    return NextResponse.json(dashboard);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to load dashboard snapshot.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
