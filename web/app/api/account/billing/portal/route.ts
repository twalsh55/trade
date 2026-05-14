import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { createBillingPortalSession } from "@/lib/api";
import { BRIVOLY_SESSION_COOKIE, LEGACY_TRADE_SESSION_COOKIE } from "@/lib/auth";

async function getSessionToken() {
  const cookieStore = await cookies();
  return cookieStore.get(BRIVOLY_SESSION_COOKIE)?.value ?? cookieStore.get(LEGACY_TRADE_SESSION_COOKIE)?.value ?? null;
}

export async function POST(request: Request) {
  const sessionToken = await getSessionToken();
  if (!sessionToken) {
    return NextResponse.json({ error: "Authentication required." }, { status: 401 });
  }

  const payload = (await request.json().catch(() => null)) as { return_url?: string | null } | null;

  try {
    const session = await createBillingPortalSession(payload ?? {}, { sessionToken });
    return NextResponse.json(session);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to create billing portal session.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
