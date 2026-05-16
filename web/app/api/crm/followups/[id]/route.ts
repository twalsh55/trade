import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { ApiError, updateCrmFollowUp } from "@/lib/api";
import { BRIVOLY_SESSION_COOKIE, LEGACY_TRADE_SESSION_COOKIE } from "@/lib/auth";

type Context = {
  params: Promise<{ id: string }>;
};

export async function PATCH(request: NextRequest, context: Context) {
  const { id } = await context.params;
  const cookieStore = await cookies();
  const sessionToken =
    cookieStore.get(BRIVOLY_SESSION_COOKIE)?.value ?? cookieStore.get(LEGACY_TRADE_SESSION_COOKIE)?.value ?? null;

  if (!sessionToken) {
    return NextResponse.json({ error: "Authentication required." }, { status: 401 });
  }

  const payload = (await request.json().catch(() => null)) as
    | { action?: "complete" | "snooze" | "note"; snooze_hours?: number; note_body?: string }
    | null;

  if (!payload?.action) {
    return NextResponse.json({ error: "Action is required." }, { status: 422 });
  }

  const normalizedPayload =
    payload.action === "complete"
      ? { action: "complete" as const }
      : payload.action === "note"
        ? { action: "note" as const, note_body: payload.note_body }
      : { action: "snooze" as const, snooze_hours: payload.snooze_hours };

  try {
    const overview = await updateCrmFollowUp(id, normalizedPayload, { sessionToken });
    return NextResponse.json(overview);
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }
    const message = error instanceof Error ? error.message : "Unable to update CRM follow-up.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
