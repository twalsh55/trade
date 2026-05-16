import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { ApiError, commitCrmImport } from "@/lib/api";
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
    const result = await commitCrmImport(payload, { sessionToken });
    return NextResponse.json(result);
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }
    const message = error instanceof Error ? error.message : "Unable to import CRM rows.";
    return NextResponse.json({ error: message }, { status: 422 });
  }
}

async function buildImportPayload(request: NextRequest) {
  const formData = await request.formData();
  const sourceType = formData.get("source_type");
  const fieldMapping = parseFieldMapping(formData.get("field_mapping"));
  if (sourceType !== "file_upload" && sourceType !== "google_sheets") {
    throw new Error("Choose a spreadsheet file or Google Sheets before importing.");
  }

  if (sourceType === "file_upload") {
    const file = formData.get("file");
    if (!hasArrayBufferReader(file)) {
      throw new Error("Choose a spreadsheet file before importing.");
    }
    const fileName = file.name || "spreadsheet";
    if (isImageFile(fileName)) {
      return {
        source_type: "image" as const,
        file_name: fileName,
        file_content_base64: toBase64(await file.arrayBuffer()),
        field_mapping: fieldMapping,
      };
    }
    if (fileName.toLowerCase().endsWith(".csv")) {
      return {
        source_type: "csv" as const,
        csv_content: await file.text(),
        field_mapping: fieldMapping,
      };
    }
    if (!fileName.toLowerCase().endsWith(".xlsx") && !fileName.toLowerCase().endsWith(".xls")) {
      throw new Error("Upload a supported spreadsheet file: .csv, .xlsx, or .xls.");
    }
    return {
      source_type: "excel" as const,
      file_name: fileName,
      file_content_base64: toBase64(await file.arrayBuffer()),
      field_mapping: fieldMapping,
    };
  }

  const sheetUrl = String(formData.get("sheet_url") || "").trim();
  if (!sheetUrl) {
    throw new Error("Paste a Google Sheets URL before importing.");
  }
  return {
    source_type: "google_sheets" as const,
    sheet_url: sheetUrl,
    field_mapping: fieldMapping,
  };
}

function hasArrayBufferReader(value: FormDataEntryValue | null): value is File {
  return typeof value === "object" && value !== null && typeof value.arrayBuffer === "function" && typeof value.text === "function";
}

function parseFieldMapping(value: FormDataEntryValue | null): Record<string, string | null> | undefined {
  const raw = String(value || "").trim();
  if (!raw) {
    return undefined;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error("Column mapping data is invalid.");
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Column mapping data is invalid.");
  }
  return Object.fromEntries(
    Object.entries(parsed as Record<string, unknown>).map(([key, field]) => [key, typeof field === "string" ? field : null]),
  );
}

function toBase64(buffer: ArrayBuffer): string {
  return Buffer.from(buffer).toString("base64");
}

function isImageFile(fileName: string): boolean {
  const normalized = fileName.toLowerCase();
  return normalized.endsWith(".png") || normalized.endsWith(".jpg") || normalized.endsWith(".jpeg") || normalized.endsWith(".webp");
}
