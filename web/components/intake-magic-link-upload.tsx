"use client";

import { useState } from "react";

type UploadState =
  | { kind: "idle"; message: string | null }
  | { kind: "submitting"; message: string }
  | { kind: "success"; message: string }
  | { kind: "error"; message: string };

export function IntakeMagicLinkUpload({ token }: { token: string }) {
  const [file, setFile] = useState<File | null>(null);
  const [state, setState] = useState<UploadState>({ kind: "idle", message: null });

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setState({ kind: "error", message: "Choose a note image before uploading." });
      return;
    }

    const payload = new FormData();
    payload.set("file", file, file.name);
    setState({ kind: "submitting", message: "Uploading your note image into Brivoly..." });

    const response = await fetch(`/api/intake/${encodeURIComponent(token)}`, {
      method: "POST",
      body: payload,
    });
    const body = (await response.json().catch(() => null)) as
      | { message?: string; imported_count?: number; skipped_duplicates?: number; skipped_invalid?: number; error?: string }
      | null;

    if (!response.ok) {
      setState({ kind: "error", message: body?.error || "Unable to import this note image right now." });
      return;
    }

    const importedCount = typeof body?.imported_count === "number" ? body.imported_count : 0;
    const duplicateCount = typeof body?.skipped_duplicates === "number" ? body.skipped_duplicates : 0;
    const invalidCount = typeof body?.skipped_invalid === "number" ? body.skipped_invalid : 0;
    const details = [`Imported ${importedCount}`];
    if (duplicateCount) {
      details.push(`Skipped duplicates ${duplicateCount}`);
    }
    if (invalidCount) {
      details.push(`Skipped invalid ${invalidCount}`);
    }
    setState({
      kind: "success",
      message: body?.message ? `${body.message} ${details.join(" · ")}.` : `Brivoly imported your note image. ${details.join(" · ")}.`,
    });
  }

  return (
    <form onSubmit={handleSubmit} className="mt-6 space-y-4 rounded-[1.75rem] border bg-white/92 p-6 shadow-sm">
      <div>
        <label htmlFor="intake-file" className="text-sm font-medium text-slate-900">
          Note image
        </label>
        <input
          id="intake-file"
          type="file"
          accept="image/png,image/jpeg,image/webp"
          onChange={(event) => {
            setFile(event.currentTarget.files?.[0] ?? null);
            setState({ kind: "idle", message: null });
          }}
          className="mt-2 block w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 file:mr-4 file:rounded-full file:border-0 file:bg-slate-900 file:px-4 file:py-2 file:text-sm file:font-medium file:text-white"
        />
      </div>

      <button
        type="submit"
        disabled={state.kind === "submitting"}
        className="inline-flex items-center rounded-full bg-slate-950 px-5 py-3 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {state.kind === "submitting" ? "Importing..." : "Upload into CRM"}
      </button>

      {state.message ? (
        <div
          className={`rounded-[1.3rem] border px-4 py-4 text-sm leading-6 ${
            state.kind === "error"
              ? "border-rose-200 bg-rose-50 text-rose-900"
              : state.kind === "success"
                ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                : "border-slate-200 bg-slate-50 text-slate-700"
          }`}
        >
          {state.message}
        </div>
      ) : null}
    </form>
  );
}
