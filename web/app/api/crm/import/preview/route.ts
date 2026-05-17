import { NextRequest, NextResponse } from "next/server";

import { ApiError, previewCrmImport } from "@/lib/api";
import { getServerApiAuthOptions } from "@/lib/server-auth";

export async function POST(request: NextRequest) {
  const { sessionToken, cookieHeader } = await getServerApiAuthOptions();

  try {
    const payload = await buildImportPayload(request);
    const preview = await previewCrmImport(payload, { sessionToken, cookieHeader });
    return NextResponse.json(preview);
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }
    const message = error instanceof Error ? error.message : "Unable to preview this context right now.";
    return NextResponse.json({ error: message }, { status: 422 });
  }
}

async function buildImportPayload(request: NextRequest) {
  const formData = await request.formData();
  const sourceType = formData.get("source_type");
  const fieldMapping = parseFieldMapping(formData.get("field_mapping"));
  const clarificationAnswers = parseClarificationAnswers(formData.get("clarification_answers"));
  const rowOverrides = parseRowOverrides(formData.get("row_overrides"));
  if (sourceType !== "file_upload" && sourceType !== "google_sheets") {
    throw new Error("Choose a spreadsheet file or Google Sheets before previewing.");
  }

  if (sourceType === "file_upload") {
    const file = formData.get("file");
    if (!hasArrayBufferReader(file)) {
      throw new Error("Choose a spreadsheet file before previewing.");
    }
    const fileName = file.name || "spreadsheet";
    if (isImageFile(fileName)) {
      return {
        source_type: "image" as const,
        file_name: fileName,
        file_content_base64: toBase64(await file.arrayBuffer()),
        field_mapping: fieldMapping,
        clarification_answers: clarificationAnswers,
        row_overrides: rowOverrides,
      };
    }
    if (fileName.toLowerCase().endsWith(".csv")) {
      return {
        source_type: "csv" as const,
        csv_content: await file.text(),
        field_mapping: fieldMapping,
        clarification_answers: clarificationAnswers,
        row_overrides: rowOverrides,
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
      clarification_answers: clarificationAnswers,
      row_overrides: rowOverrides,
    };
  }

  const sheetUrl = String(formData.get("sheet_url") || "").trim();
  if (!sheetUrl) {
    throw new Error("Paste a Google Sheets URL before previewing.");
  }
  return {
    source_type: "google_sheets" as const,
    sheet_url: sheetUrl,
    field_mapping: fieldMapping,
    clarification_answers: clarificationAnswers,
    row_overrides: rowOverrides,
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

function parseClarificationAnswers(value: FormDataEntryValue | null): Record<string, string> | undefined {
  const raw = String(value || "").trim();
  if (!raw) {
    return undefined;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error("AI clarification answers are invalid.");
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("AI clarification answers are invalid.");
  }
  return Object.fromEntries(
    Object.entries(parsed as Record<string, unknown>).flatMap(([key, field]) =>
      typeof field === "string" && field.trim() ? [[key, field.trim()]] : [],
    ),
  );
}

function parseRowOverrides(value: FormDataEntryValue | null): Record<string, Record<string, string>> | undefined {
  const raw = String(value || "").trim();
  if (!raw) {
    return undefined;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error("Row fixes are invalid.");
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Row fixes are invalid.");
  }
  const normalized = Object.fromEntries(
    Object.entries(parsed as Record<string, unknown>).flatMap(([rowNumber, fields]) => {
      if (!fields || typeof fields !== "object" || Array.isArray(fields)) {
        return [];
      }
      const normalizedFields = Object.fromEntries(
        Object.entries(fields as Record<string, unknown>).flatMap(([fieldName, fieldValue]) =>
          typeof fieldValue === "string" && fieldValue.trim() ? [[fieldName, fieldValue.trim()]] : [],
        ),
      );
      return Object.keys(normalizedFields).length ? [[rowNumber, normalizedFields]] : [];
    }),
  );
  return Object.keys(normalized).length ? normalized : undefined;
}

function toBase64(buffer: ArrayBuffer): string {
  return Buffer.from(buffer).toString("base64");
}

function isImageFile(fileName: string): boolean {
  const normalized = fileName.toLowerCase();
  return normalized.endsWith(".png") || normalized.endsWith(".jpg") || normalized.endsWith(".jpeg") || normalized.endsWith(".webp");
}
