import { NextRequest, NextResponse } from "next/server";

import { ApiError, ingestCrmCalendarEvent } from "@/lib/api";
import { getServerApiAuthOptions } from "@/lib/server-auth";

export async function POST(request: NextRequest) {
  const { sessionToken, cookieHeader } = await getServerApiAuthOptions();
  const payload = (await request.json().catch(() => null)) as
    | {
        connection_id?: string | null;
        provider?: "google_calendar" | "outlook_calendar";
        event_id?: string;
        title?: string;
        starts_at?: string;
        attendee_emails?: string[];
        notes?: string;
      }
    | null;

  if (!payload?.provider || !payload?.event_id || !payload?.title || !payload?.starts_at || !payload?.attendee_emails?.length) {
    return NextResponse.json(
      { error: "provider, event_id, title, starts_at, and attendee_emails are required." },
      { status: 422 },
    );
  }

  try {
    const overview = await ingestCrmCalendarEvent(
      {
        connection_id: payload.connection_id ?? null,
        provider: payload.provider,
        event_id: payload.event_id,
        title: payload.title,
        starts_at: payload.starts_at,
        attendee_emails: payload.attendee_emails,
        notes: payload.notes ?? "",
      },
      { sessionToken, cookieHeader },
    );
    return NextResponse.json(overview);
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }
    const message = error instanceof Error ? error.message : "Unable to bring this meeting into Brivoly right now.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
