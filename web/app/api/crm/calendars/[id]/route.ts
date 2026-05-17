import { NextResponse } from "next/server";

import { ApiError, deleteCrmCalendarConnection, updateCrmCalendarConnection } from "@/lib/api";
import { getServerApiAuthOptions } from "@/lib/server-auth";

type RouteContext = {
  params: Promise<{ id: string }>;
};

export async function DELETE(_request: Request, context: RouteContext) {
  const { sessionToken, cookieHeader } = await getServerApiAuthOptions();
  const { id } = await context.params;

  try {
    const result = await deleteCrmCalendarConnection(id, { sessionToken, cookieHeader });
    return NextResponse.json(result);
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }
    const message = error instanceof Error ? error.message : "Unable to disconnect the calendar right now.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

export async function PATCH(request: Request, context: RouteContext) {
  const { sessionToken, cookieHeader } = await getServerApiAuthOptions();
  const { id } = await context.params;
  const payload = (await request.json().catch(() => null)) as { background_sync_enabled?: boolean } | null;

  if (typeof payload?.background_sync_enabled !== "boolean") {
    return NextResponse.json({ error: "background_sync_enabled is required." }, { status: 422 });
  }

  try {
    const result = await updateCrmCalendarConnection(
      id,
      { background_sync_enabled: payload.background_sync_enabled },
      { sessionToken, cookieHeader },
    );
    return NextResponse.json(result);
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }
    const message = error instanceof Error ? error.message : "Unable to update the calendar right now.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
