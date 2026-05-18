"use client";

import { useState } from "react";

type UploadState =
  | { kind: "idle"; message: string | null }
  | { kind: "submitting"; message: string }
  | { kind: "success"; message: string }
  | { kind: "error"; message: string };

export function IntakeMagicLinkUpload({ token }: { token: string }) {
  const [file, setFile] = useState<File | null>(null);
  const [state, setState] = useState<UploadState>({
    kind: "idle",
    message: null,
  });

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setState({
        kind: "error",
        message: "Choose a screenshot or note image before sending it.",
      });
      return;
    }

    const payload = new FormData();
    payload.set("file", file, file.name);
    setState({ kind: "submitting", message: "Sending your update..." });

    const response = await fetch(`/api/intake/${encodeURIComponent(token)}`, {
      method: "POST",
      body: payload,
    });
    const body = (await response.json().catch(() => null)) as {
      message?: string;
      imported_count?: number;
      skipped_duplicates?: number;
      skipped_invalid?: number;
      error?: string;
    } | null;

    if (!response.ok) {
      setState({
        kind: "error",
        message: body?.error || "Unable to send this update right now.",
      });
      return;
    }

    const importedCount =
      typeof body?.imported_count === "number" ? body.imported_count : 0;
    const duplicateCount =
      typeof body?.skipped_duplicates === "number"
        ? body.skipped_duplicates
        : 0;
    const invalidCount =
      typeof body?.skipped_invalid === "number" ? body.skipped_invalid : 0;
    const details = [`Imported ${importedCount}`];
    if (duplicateCount) {
      details.push(`Skipped duplicates ${duplicateCount}`);
    }
    if (invalidCount) {
      details.push(`Skipped invalid ${invalidCount}`);
    }
    setState({
      kind: "success",
      message: body?.message
        ? `${body.message} ${details.join(" · ")}.`
        : `Your update was sent. ${details.join(" · ")}.`,
    });
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="mt-6 space-y-4 rounded-[1.75rem] border bg-white/92 p-6 shadow-sm"
    >
      <div className="rounded-[1.3rem] border bg-slate-50 px-4 py-4 text-sm leading-6 text-slate-700">
        <p className="font-medium text-slate-900">No login is needed.</p>
        <p className="mt-1">
          Send a screenshot, whiteboard photo, handwritten note, or other small
          update from your phone in a few taps.
        </p>
      </div>

      <div className="rounded-[1.3rem] border bg-slate-50 px-4 py-4 text-sm leading-6 text-slate-700">
        <p className="font-medium text-slate-900">Best results</p>
        <p className="mt-1">
          One clear photo or screenshot is enough. Keep the important part in
          frame and Brivoly will bring the useful context back into memory.
        </p>
      </div>

      <div>
        <label
          htmlFor="intake-file"
          className="text-sm font-medium text-slate-900"
        >
          Add the update
        </label>
        <input
          id="intake-file"
          type="file"
          accept="image/png,image/jpeg,image/webp"
          capture="environment"
          onChange={(event) => {
            setFile(event.currentTarget.files?.[0] ?? null);
            setState({ kind: "idle", message: null });
          }}
          className="mt-2 block w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 file:mr-4 file:rounded-full file:border-0 file:bg-slate-900 file:px-4 file:py-2 file:text-sm file:font-medium file:text-white"
        />
        <p className="mt-2 text-xs text-slate-500">
          PNG, JPG, or WEBP. Phone camera capture works too.
        </p>
      </div>

      {file ? (
        <div className="rounded-[1.3rem] border bg-slate-50 px-4 py-4 text-sm leading-6 text-slate-700">
          <p className="font-medium text-slate-900">Ready to send</p>
          <p className="mt-1 break-all">{file.name}</p>
        </div>
      ) : null}

      <button
        type="submit"
        disabled={state.kind === "submitting"}
        className="inline-flex w-full items-center justify-center rounded-full bg-slate-950 px-5 py-3 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
      >
        {state.kind === "submitting" ? "Sending..." : "Send update"}
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
