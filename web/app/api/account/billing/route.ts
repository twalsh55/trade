import { NextResponse } from "next/server";

import { getBillingOverview } from "@/lib/api";
import { getServerApiAuthOptions } from "@/lib/server-auth";

export async function GET() {
  const { sessionToken, cookieHeader } = await getServerApiAuthOptions();

  try {
    const billing = await getBillingOverview({ sessionToken, cookieHeader });
    return NextResponse.json(billing);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to load billing status.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
