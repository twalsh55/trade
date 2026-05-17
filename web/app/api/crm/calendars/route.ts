import { NextRequest, NextResponse } from "next/server";

import { ApiError, connectCrmCalendar, listCrmCalendarConnections } from "@/lib/api";
import { getServerApiAuthOptions } from "@/lib/server-auth";

export async function GET() {
  const { sessionToken, cookieHeader } = await getServerApiAuthOptions();

  try {
    const items = await listCrmCalendarConnections({ sessionToken, cookieHeader });
    return NextResponse.json({ items });
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }
    const message = error instanceof Error ? error.message : "Unable to load calendar connections.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  const { sessionToken, cookieHeader } = await getServerApiAuthOptions();
  const payload = (await request.json().catch(() => null)) as
    | {
        provider?: "google_calendar" | "outlook_calendar";
        calendar_address?: string;
        display_name?: string;
      }
    | null;

  if (!payload?.provider || !payload?.calendar_address) {
    return NextResponse.json({ error: "provider and calendar_address are required." }, { status: 422 });
  }

  try {
    const connection = await connectCrmCalendar(
      {
        provider: payload.provider,
        calendar_address: payload.calendar_address,
        display_name: payload.display_name ?? "",
      },
      { sessionToken, cookieHeader },
    );
    return NextResponse.json(connection);
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }
    const message = error instanceof Error ? error.message : "Unable to connect the calendar right now.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
