import { NextRequest, NextResponse } from "next/server";

import { ApiError, sendCrmFollowUpEmail } from "@/lib/api";
import { getServerApiAuthOptions } from "@/lib/server-auth";

type RouteContext = {
  params: Promise<{ id: string }>;
};

export async function POST(request: NextRequest, context: RouteContext) {
  const { sessionToken, cookieHeader } = await getServerApiAuthOptions();
  const { id } = await context.params;
  const payload = (await request.json().catch(() => null)) as
    | {
        connection_id?: string | null;
        thread_id?: string | null;
        subject?: string;
        body?: string;
      }
    | null;

  if (!payload?.subject || !payload?.body) {
    return NextResponse.json({ error: "subject and body are required." }, { status: 422 });
  }

  try {
    const result = await sendCrmFollowUpEmail(
      id,
      {
        connection_id: payload.connection_id ?? null,
        thread_id: payload.thread_id ?? null,
        subject: payload.subject,
        body: payload.body,
      },
      { sessionToken, cookieHeader },
    );
    return NextResponse.json(result);
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }
    const message = error instanceof Error ? error.message : "Unable to send this note right now.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
