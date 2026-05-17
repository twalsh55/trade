import { NextRequest, NextResponse } from "next/server";

import { ApiError, updateCrmFollowUp } from "@/lib/api";
import { getServerApiAuthOptions } from "@/lib/server-auth";

type Context = {
  params: Promise<{ id: string }>;
};

export async function PATCH(request: NextRequest, context: Context) {
  const { id } = await context.params;
  const { sessionToken, cookieHeader } = await getServerApiAuthOptions();

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
    const overview = await updateCrmFollowUp(id, normalizedPayload, { sessionToken, cookieHeader });
    return NextResponse.json(overview);
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }
    const message = error instanceof Error ? error.message : "Unable to update CRM follow-up.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
