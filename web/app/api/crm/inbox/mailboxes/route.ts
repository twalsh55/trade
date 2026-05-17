import { NextRequest, NextResponse } from "next/server";

import { ApiError, connectCrmMailbox, listCrmMailboxConnections } from "@/lib/api";
import { getServerApiAuthOptions } from "@/lib/server-auth";

export async function GET() {
  const { sessionToken, cookieHeader } = await getServerApiAuthOptions();

  try {
    const items = await listCrmMailboxConnections({ sessionToken, cookieHeader });
    return NextResponse.json({ items });
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }
    const message = error instanceof Error ? error.message : "Unable to load mailbox connections.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  const { sessionToken, cookieHeader } = await getServerApiAuthOptions();
  const payload = (await request.json().catch(() => null)) as
    | {
        provider?: "gmail" | "outlook";
        email_address?: string;
        display_name?: string;
      }
    | null;

  if (!payload?.provider || !payload?.email_address) {
    return NextResponse.json({ error: "provider and email_address are required." }, { status: 422 });
  }

  try {
    const connection = await connectCrmMailbox(
      {
        provider: payload.provider,
        email_address: payload.email_address,
        display_name: payload.display_name ?? "",
      },
      { sessionToken, cookieHeader },
    );
    return NextResponse.json(connection);
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }
    const message = error instanceof Error ? error.message : "Unable to connect the mailbox right now.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
