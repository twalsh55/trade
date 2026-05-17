import { NextRequest, NextResponse } from "next/server";

import { ApiError, generateCrmFollowUpEmailDraft } from "@/lib/api";
import { getServerApiAuthOptions } from "@/lib/server-auth";

type Context = {
  params: Promise<{ id: string }>;
};

export async function POST(request: NextRequest, context: Context) {
  const { id } = await context.params;
  const { sessionToken, cookieHeader } = await getServerApiAuthOptions();

  const payload = (await request.json().catch(() => null)) as
    | { objective?: "follow_up" | "recap" | "revive" | "close_loop"; tone?: "warm" | "direct" | "confident"; length?: "short" | "medium" }
    | null;

  try {
    const draft = await generateCrmFollowUpEmailDraft(
      id,
      {
        objective: payload?.objective ?? "follow_up",
        tone: payload?.tone ?? "warm",
        length: payload?.length ?? "short",
      },
      { sessionToken, cookieHeader },
    );
    return NextResponse.json(draft);
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }
    const message = error instanceof Error ? error.message : "Unable to generate CRM email draft.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
