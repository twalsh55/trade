import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { getAccountSettings, updateAccountSettings } from "@/lib/api";
import { TRADE_SESSION_COOKIE } from "@/lib/auth";
import type { AccountSettings } from "@/lib/types";

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
    const settings = await getAccountSettings({ sessionToken });
    return NextResponse.json(settings);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to load account settings.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

export async function PUT(request: Request) {
  const sessionToken = await getSessionToken();
  if (!sessionToken) {
    return NextResponse.json({ error: "Authentication required." }, { status: 401 });
  }

  const payload = (await request.json().catch(() => null)) as AccountSettings | null;
  if (!payload) {
    return NextResponse.json({ error: "Invalid settings payload." }, { status: 400 });
  }

  try {
    const settings = await updateAccountSettings(payload, { sessionToken });
    return NextResponse.json(settings);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to update account settings.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
