import { NextRequest, NextResponse } from "next/server";

import { ApiError, ingestCrmInboxThread } from "@/lib/api";
import { getServerApiAuthOptions } from "@/lib/server-auth";

export async function POST(request: NextRequest) {
  const { sessionToken, cookieHeader } = await getServerApiAuthOptions();

  const payload = (await request.json().catch(() => null)) as
    | {
        source?: string;
        thread_id?: string;
        messages?: Array<{
          message_id?: string;
          sent_at?: string;
          direction?: "inbound" | "outbound";
          from_email?: string;
          from_name?: string;
          to_emails?: string[];
          subject?: string;
          body_text?: string;
          snippet?: string;
        }>;
      }
    | null;

  if (!payload?.thread_id || !payload?.messages?.length) {
    return NextResponse.json({ error: "thread_id and at least one message are required." }, { status: 422 });
  }

  try {
    const overview = await ingestCrmInboxThread(
      {
        source: payload.source ?? "api",
        thread_id: payload.thread_id,
        messages: payload.messages.map((item) => ({
          message_id: item.message_id ?? "",
          sent_at: item.sent_at ?? "",
          direction: item.direction ?? "inbound",
          from_email: item.from_email ?? "",
          from_name: item.from_name ?? "",
          to_emails: item.to_emails ?? [],
          subject: item.subject ?? "",
          body_text: item.body_text ?? "",
          snippet: item.snippet ?? "",
        })),
      },
      { sessionToken, cookieHeader },
    );
    return NextResponse.json(overview);
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }
    const message = error instanceof Error ? error.message : "Unable to sync inbox thread.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
