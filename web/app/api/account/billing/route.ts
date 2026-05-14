import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { getBillingOverview } from "@/lib/api";
import { TRADE_SESSION_COOKIE } from "@/lib/auth";

async function getSessionToken() {
  const cookieStore = await cookies();
  return cookieStore.get(TRADE_SESSION_COOKIE)?.value ?? null;
}

export async function GET() {
  const sessionToken = await getSessionToken();
  if (!sessionToken) {
    return NextResponse.json({ error: "Authentication required." }, { status: 401 });
  }

  try {
    const billing = await getBillingOverview({ sessionToken });
    return NextResponse.json(billing);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to load billing status.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
