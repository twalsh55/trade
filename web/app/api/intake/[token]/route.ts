import { NextRequest, NextResponse } from "next/server";

const API_BASE_URL =
  process.env.BRIVOLY_API_BASE_URL ??
  process.env.TRADE_API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://127.0.0.1:8000";

export async function POST(request: NextRequest, context: { params: Promise<{ token: string }> }) {
  const { token } = await context.params;
  if (!token.trim()) {
    return NextResponse.json({ error: "Missing intake token." }, { status: 400 });
  }

  const inbound = await request.formData();
  const file = inbound.get("file");
  if (!(file instanceof File)) {
    return NextResponse.json({ error: "Choose an image before uploading." }, { status: 422 });
  }

  const payload = new FormData();
  const fileName = file.name || "crm-note-upload";
  const fileBytes = Buffer.from(await file.arrayBuffer()).toString("base64");

  const response = await fetch(`${API_BASE_URL}/api/crm/intake/upload`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({
      intake_token: token,
      file_name: fileName,
      file_content_base64: fileBytes,
    }),
    cache: "no-store",
  });

  const bodyText = await response.text().catch(() => "");
  let parsed: unknown = null;
  if (bodyText) {
    try {
      parsed = JSON.parse(bodyText);
    } catch {
      parsed = null;
    }
  }

  if (!response.ok) {
    const error =
      typeof parsed === "object" &&
      parsed !== null &&
      "detail" in parsed &&
      typeof (parsed as { detail?: unknown }).detail === "string"
        ? ((parsed as { detail: string }).detail)
        : typeof parsed === "object" &&
            parsed !== null &&
            "error" in parsed &&
            typeof (parsed as { error?: unknown }).error === "string"
          ? ((parsed as { error: string }).error)
          : bodyText.trim() || "Unable to import this note image.";
    return NextResponse.json({ error }, { status: response.status });
  }

  return NextResponse.json(parsed ?? {});
}
