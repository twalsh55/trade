import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { ApiError, previewCrmImport } from "@/lib/api";
import { BRIVOLY_SESSION_COOKIE, LEGACY_TRADE_SESSION_COOKIE } from "@/lib/auth";

export async function POST(request: NextRequest) {
  const cookieStore = await cookies();
  const sessionToken =
    cookieStore.get(BRIVOLY_SESSION_COOKIE)?.value ?? cookieStore.get(LEGACY_TRADE_SESSION_COOKIE)?.value ?? null;

  if (!sessionToken) {
    return NextResponse.json({ error: "Authentication required." }, { status: 401 });
  }

  try {
    const payload = await buildImportPayload(request);
    const preview = await previewCrmImport(payload, { sessionToken });
    return NextResponse.json(preview);
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }
    const message = error instanceof Error ? error.message : "Unable to preview CRM import.";
    return NextResponse.json({ error: message }, { status: 422 });
  }
}

async function buildImportPayload(request: NextRequest) {
  const formData = await request.formData();
  const sourceType = formData.get("source_type");
  if (sourceType !== "csv" && sourceType !== "google_sheets") {
    throw new Error("Choose CSV upload or Google Sheets before previewing.");
  }

  if (sourceType === "csv") {
    const file = formData.get("file");
    if (!hasTextReader(file)) {
      throw new Error("Choose a CSV file before previewing.");
    }
    return {
      source_type: "csv" as const,
      csv_content: await file.text(),
    };
  }

  const sheetUrl = String(formData.get("sheet_url") || "").trim();
  if (!sheetUrl) {
    throw new Error("Paste a Google Sheets URL before previewing.");
  }
  return {
    source_type: "google_sheets" as const,
    sheet_url: sheetUrl,
  };
}

function hasTextReader(value: FormDataEntryValue | null): value is File {
  return typeof value === "object" && value !== null && typeof value.text === "function";
}
