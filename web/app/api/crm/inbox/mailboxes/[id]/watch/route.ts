import { NextResponse } from "next/server";

import { ApiError, renewCrmMailboxWatch } from "@/lib/api";
import { getServerApiAuthOptions } from "@/lib/server-auth";

type RouteContext = {
  params: Promise<{ id: string }>;
};

export async function POST(_: Request, context: RouteContext) {
  const { id } = await context.params;
  const { sessionToken, cookieHeader } = await getServerApiAuthOptions();

  try {
    const result = await renewCrmMailboxWatch(id, { sessionToken, cookieHeader });
    return NextResponse.json(result);
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }
    const message = error instanceof Error ? error.message : "Unable to renew mailbox watch coverage right now.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
