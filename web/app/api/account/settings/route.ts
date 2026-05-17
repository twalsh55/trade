import { NextResponse } from "next/server";

import { getAccountSettings, updateAccountSettings } from "@/lib/api";
import { getServerApiAuthOptions } from "@/lib/server-auth";
import type { AccountSettings } from "@/lib/types";

export async function GET() {
  const { sessionToken, cookieHeader } = await getServerApiAuthOptions();

  try {
    const settings = await getAccountSettings({ sessionToken, cookieHeader });
    return NextResponse.json(settings);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to load account settings.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

export async function PUT(request: Request) {
  const { sessionToken, cookieHeader } = await getServerApiAuthOptions();

  const payload = (await request.json().catch(() => null)) as AccountSettings | null;
  if (!payload) {
    return NextResponse.json({ error: "Invalid settings payload." }, { status: 400 });
  }

  try {
    const settings = await updateAccountSettings(payload, { sessionToken, cookieHeader });
    return NextResponse.json(settings);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to update account settings.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
