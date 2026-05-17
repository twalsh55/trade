import { NextResponse } from "next/server";

import { getCrmFollowUpOverview } from "@/lib/api";
import { getServerApiAuthOptions } from "@/lib/server-auth";

export async function GET() {
  const { sessionToken, cookieHeader } = await getServerApiAuthOptions();

  try {
    const overview = await getCrmFollowUpOverview({ sessionToken, cookieHeader });
    return NextResponse.json(overview);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to load your relationship list right now.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
