import { NextRequest, NextResponse } from "next/server";

import { eraseAccountPrivacyData } from "@/lib/api";
import { getServerApiAuthOptions } from "@/lib/server-auth";

export async function POST(request: NextRequest) {
  const { sessionToken, cookieHeader } = await getServerApiAuthOptions();
  const payload = (await request.json().catch(() => null)) as { scope?: "relationship_memory" | "all_memory"; confirm?: boolean } | null;

  if (!payload?.scope || typeof payload.confirm !== "boolean") {
    return NextResponse.json({ error: "scope and confirm are required." }, { status: 422 });
  }

  try {
    const result = await eraseAccountPrivacyData({ scope: payload.scope, confirm: payload.confirm }, { sessionToken, cookieHeader });
    return NextResponse.json(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to erase account data.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
