"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";

import { Button } from "@/components/ui/button";
import type {
  AccountSettings,
  BillingOverview,
  CRMFollowUpOverview,
  CRMImportHeaderMapping,
  CRMImportPreview,
  CRMImportPreviewRow,
  CRMLeadFollowUp,
  CRMRemoteIntakeChannel,
} from "@/lib/types";

export function CRMFollowUpWorkspace({
  initialOverview,
  initialSettings,
  initialBilling,
  initialIntakeChannel,
}: {
  initialOverview: CRMFollowUpOverview;
  initialSettings: AccountSettings | null;
  initialBilling: BillingOverview | null;
  initialIntakeChannel: CRMRemoteIntakeChannel | null;
}) {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [overview, setOverview] = useState(initialOverview);
  const [settings, setSettings] = useState<AccountSettings | null>(initialSettings);
  const [selectedLeadId, setSelectedLeadId] = useState(initialOverview.items[0]?.id ?? null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [noteDraft, setNoteDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sourceType, setSourceType] = useState<"file_upload" | "google_sheets">("file_upload");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [sheetUrl, setSheetUrl] = useState("");
  const [importPreview, setImportPreview] = useState<CRMImportPreview | null>(null);
  const [importFieldMapping, setImportFieldMapping] = useState<Record<string, string>>({});
  const [isImportMappingDirty, setIsImportMappingDirty] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [importStatus, setImportStatus] = useState<string | null>(null);
  const [aiPromptDraft, setAiPromptDraft] = useState(initialSettings?.crm_ai_prompt ?? "");
  const [aiFormatsDraft, setAiFormatsDraft] = useState((initialSettings?.crm_preferred_import_formats ?? []).join(", "));
  const [aiSettingsStatus, setAiSettingsStatus] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const [isImportPending, startImportTransition] = useTransition();
  const [isAiSettingsPending, startAiSettingsTransition] = useTransition();

  useEffect(() => {
    if (!selectedLeadId && initialOverview.items[0]) {
      setSelectedLeadId(initialOverview.items[0].id);
    }
  }, [initialOverview.items, selectedLeadId]);

  const selectedLead = overview.items.find((item) => item.id === selectedLeadId) ?? overview.items[0] ?? null;
  const advancedAiUnlocked = hasAdvancedAiAccess(initialBilling);

  function runAction(
    followUpId: string,
    payload: { action: "complete" | "snooze" | "note"; snooze_hours?: number; note_body?: string },
    afterSuccess?: () => void,
  ) {
    setPendingId(followUpId);
    setError(null);
    startTransition(async () => {
      try {
        const response = await fetch(`/api/crm/followups/${followUpId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        const data = (await response.json().catch(() => null)) as CRMFollowUpOverview | { error?: string } | null;
        if (!response.ok || !data || !("items" in data)) {
          throw new Error((data && "error" in data && data.error) || "Unable to update follow-up.");
        }

        setOverview(data);
        if (followUpId === selectedLeadId && !data.items.some((item) => item.id === followUpId)) {
          setSelectedLeadId(data.items[0]?.id ?? null);
        }
        afterSuccess?.();
        router.refresh();
      } catch (actionError) {
        setError(actionError instanceof Error ? actionError.message : "Unable to update follow-up.");
      } finally {
        setPendingId(null);
      }
    });
  }

  function saveNote() {
    if (!selectedLead) {
      return;
    }
    runAction(
      selectedLead.id,
      { action: "note", note_body: noteDraft },
      () => setNoteDraft(""),
    );
  }

  function buildImportFormData() {
    const formData = new FormData();
    formData.set("source_type", sourceType);
    if (Object.keys(importFieldMapping).length) {
      formData.set("field_mapping", JSON.stringify(importFieldMapping));
    }
    if (sourceType === "file_upload") {
      if (!selectedFile) {
        throw new Error("Choose a spreadsheet file first.");
      }
      if (isImageFile(selectedFile.name) && !advancedAiUnlocked) {
        throw new Error("AI note image intake is available on active or trialing paid plans.");
      }
      formData.set("file", selectedFile);
      return formData;
    }
    if (!sheetUrl.trim()) {
      throw new Error("Paste a Google Sheets URL first.");
    }
    formData.set("sheet_url", sheetUrl.trim());
    return formData;
  }

  function requestImportPreview() {
    setImportError(null);
    setImportStatus(null);
    startImportTransition(async () => {
      try {
        const response = await fetch("/api/crm/import/preview", {
          method: "POST",
          body: buildImportFormData(),
        });
        const data = (await response.json().catch(() => null)) as CRMImportPreview | { error?: string } | null;
        if (!response.ok || !data || !("rows" in data)) {
          throw new Error((data && "error" in data && data.error) || "Unable to preview import.");
        }
        setImportPreview(data);
        setImportFieldMapping(
          Object.fromEntries(
            data.header_mappings
              .filter((item) => item.mapped_field)
              .map((item) => [item.original_header, item.mapped_field as string]),
          ),
        );
        setIsImportMappingDirty(false);
        setImportStatus(`Preview ready for ${data.importable_rows} importable row${data.importable_rows === 1 ? "" : "s"}.`);
      } catch (previewError) {
        setImportPreview(null);
        setImportError(previewError instanceof Error ? previewError.message : "Unable to preview import.");
      }
    });
  }

  function commitImport() {
    setImportError(null);
    setImportStatus(null);
    startImportTransition(async () => {
      try {
        const response = await fetch("/api/crm/import", {
          method: "POST",
          body: buildImportFormData(),
        });
        const data = (await response.json().catch(() => null)) as
          | { imported_count: number; skipped_duplicates: number; skipped_invalid: number; overview: CRMFollowUpOverview }
          | { error?: string }
          | null;
        if (!response.ok || !data || !("overview" in data)) {
          throw new Error((data && "error" in data && data.error) || "Unable to import spreadsheet rows.");
        }
        setOverview(data.overview);
        setSelectedLeadId(data.overview.items[0]?.id ?? null);
        setImportPreview(null);
        setImportFieldMapping({});
        setIsImportMappingDirty(false);
        setImportStatus(
          `Imported ${data.imported_count} row${data.imported_count === 1 ? "" : "s"}, skipped ${data.skipped_duplicates} duplicates, and skipped ${data.skipped_invalid} invalid row${data.skipped_invalid === 1 ? "" : "s"}.`,
        );
        setSelectedFile(null);
        setSheetUrl("");
        if (fileInputRef.current) {
          fileInputRef.current.value = "";
        }
        router.refresh();
      } catch (commitError) {
        setImportError(commitError instanceof Error ? commitError.message : "Unable to import spreadsheet rows.");
      }
    });
  }

  function updateImportFieldMapping(header: string, field: string) {
    setImportFieldMapping((current) => ({
      ...current,
      [header]: field,
    }));
    setImportStatus(null);
    setIsImportMappingDirty(true);
  }

  function saveAiImportSettings() {
    if (!settings) {
      return;
    }
    setAiSettingsStatus("Saving AI intake preferences...");
    startAiSettingsTransition(async () => {
      const payload: AccountSettings = {
        ...settings,
        crm_ai_prompt: aiPromptDraft.trim(),
        crm_preferred_import_formats: aiFormatsDraft
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
      };
      try {
        const response = await fetch("/api/account/settings", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const body = (await response.json().catch(() => null)) as AccountSettings | { error?: string } | null;
        if (!response.ok || !body || !("benchmark" in body)) {
          throw new Error((body && "error" in body && body.error) || "Unable to save AI intake settings.");
        }
        setSettings(body);
        setAiPromptDraft(body.crm_ai_prompt);
        setAiFormatsDraft(body.crm_preferred_import_formats.join(", "));
        setAiSettingsStatus("AI intake preferences saved.");
      } catch (saveError) {
        setAiSettingsStatus(saveError instanceof Error ? saveError.message : "Unable to save AI intake settings.");
      }
    });
  }

  return (
    <>
      <section className="mt-6 grid gap-6 md:grid-cols-4">
        <MetricCard label="Open follow-ups" value={String(overview.total_open)} tone="neutral" />
        <MetricCard label="Due today" value={String(overview.due_today)} tone="warning" />
        <MetricCard label="Overdue" value={String(overview.overdue)} tone={overview.overdue > 0 ? "critical" : "positive"} />
        <MetricCard label="High priority" value={String(overview.high_priority)} tone="neutral" />
      </section>

      <section className="mt-6 rounded-[1.75rem] border bg-white/85 p-6 shadow-sm">
        <div className="grid gap-6 xl:grid-cols-[0.92fr_1.08fr]">
          <section>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Spreadsheet Import</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">Bring your lead sheet in without retyping it.</h2>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              Upload a CSV, XLSX, XLS, or note image, or paste a Google Sheets link. Brivoly normalizes messy headers, flags validation problems, and skips duplicates before anything enters the follow-up queue.
            </p>

            <div className="mt-5 flex flex-wrap gap-3">
              <Button variant={sourceType === "file_upload" ? "default" : "outline"} onClick={() => setSourceType("file_upload")}>
                Spreadsheet file
              </Button>
              <Button variant={sourceType === "google_sheets" ? "default" : "outline"} onClick={() => setSourceType("google_sheets")}>
                Google Sheets
              </Button>
            </div>

            {sourceType === "file_upload" ? (
              <section className="mt-5 rounded-[1.4rem] border bg-slate-50/80 p-5">
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Spreadsheet file</p>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv,text/csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,.xls,application/vnd.ms-excel,.png,image/png,.jpg,image/jpeg,.jpeg,image/jpeg,.webp,image/webp"
                  className="mt-3 block w-full rounded-2xl border border-dashed border-slate-300 bg-white px-4 py-5 text-sm text-slate-600"
                  onChange={(event) => {
                    setSelectedFile(event.target.files?.[0] ?? null);
                    setImportPreview(null);
                    setImportFieldMapping({});
                    setIsImportMappingDirty(false);
                    setImportStatus(null);
                    setImportError(null);
                  }}
                />
                <p className="mt-3 text-xs text-slate-500">
                  Supported uploads: CSV, XLSX, XLS, PNG, JPG, JPEG, and WEBP. Note images use paid AI intake. Suggested spreadsheet columns: contact, company, owner, status, next follow-up, and notes.
                </p>
                {selectedFile ? <p className="mt-2 text-sm font-medium text-slate-700">{selectedFile.name}</p> : null}
                {selectedFile && isImageFile(selectedFile.name) ? (
                  <p className="mt-2 text-xs text-slate-500">
                    Brivoly will use your AI Intake Profile to turn this note image into CRM-ready rows before previewing them.
                  </p>
                ) : null}
              </section>
            ) : (
              <section className="mt-5 rounded-[1.4rem] border bg-slate-50/80 p-5">
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Google Sheets URL</p>
                <input
                  value={sheetUrl}
                  onChange={(event) => {
                    setSheetUrl(event.target.value);
                    setImportPreview(null);
                    setImportFieldMapping({});
                    setIsImportMappingDirty(false);
                    setImportStatus(null);
                    setImportError(null);
                  }}
                  placeholder="https://docs.google.com/spreadsheets/d/..."
                  className="mt-3 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400"
                />
                <p className="mt-3 text-xs text-slate-500">Use a shareable Google Sheets URL. Brivoly will request the CSV export directly.</p>
              </section>
            )}

            <div className="mt-5 flex flex-wrap gap-3">
              <Button disabled={isImportPending} onClick={requestImportPreview}>
                {isImportPending ? "Checking..." : importPreview ? "Refresh preview" : "Preview import"}
              </Button>
              <Button
                variant="outline"
                disabled={isImportPending || !importPreview || importPreview.importable_rows === 0 || isImportMappingDirty}
                onClick={commitImport}
              >
                {isImportPending ? "Importing..." : "Import rows"}
              </Button>
            </div>

            {importError ? <p className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{importError}</p> : null}
            {importStatus ? <p className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{importStatus}</p> : null}
            {isImportMappingDirty ? (
              <p className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                Column mappings changed. Refresh the preview before importing so Brivoly can validate the updated layout.
              </p>
            ) : null}
          </section>

          <ImportPreviewPanel
            preview={importPreview}
            importFieldMapping={importFieldMapping}
            isImportMappingDirty={isImportMappingDirty}
            onFieldMappingChange={updateImportFieldMapping}
          />
        </div>
      </section>

      <section className="mt-6 grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <section className="rounded-[1.75rem] border bg-white/80 p-6 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Lead Follow-Up Queue</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">Who needs a follow-up next.</h2>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            Work the queue directly, then use the memory panel to keep discovery notes, context, and next-step details attached to the right lead.
          </p>
          {error ? <p className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p> : null}
          <div className="mt-6 space-y-4">
            {overview.items.map((item) => {
              const rowPending = pendingId === item.id && isPending;
              const selected = item.id === selectedLead?.id;
              return (
                <article
                  key={item.id}
                  className={`rounded-[1.5rem] border p-5 transition ${selected ? "border-slate-900 bg-white shadow-sm" : "bg-slate-50/80"}`}
                >
                  <button type="button" className="w-full text-left" onClick={() => setSelectedLeadId(item.id)}>
                    <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">
                          {item.stage} · {item.contact_channel}
                        </p>
                        <h3 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">{item.lead_name}</h3>
                        <p className="mt-1 text-sm text-slate-600">{item.company_name}</p>
                        <p className="mt-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Owner · {item.owner_name}</p>
                      </div>
                      <PriorityBadge priority={item.priority} />
                    </div>
                    <p className="mt-4 text-sm font-medium text-slate-700">Next step</p>
                    <p className="mt-1 text-sm leading-6 text-slate-600">{item.next_step}</p>
                    <div className="mt-5 grid gap-3 md:grid-cols-2">
                      <TimelineTile label="Last touched" value={formatDateTime(item.last_contacted_at)} />
                      <TimelineTile label="Next follow-up" value={formatDateTime(item.next_follow_up_at)} />
                    </div>
                  </button>
                  <div className="mt-5 flex flex-wrap gap-3">
                    <Button disabled={rowPending} onClick={() => runAction(item.id, { action: "complete" })}>
                      {rowPending ? "Updating..." : "Complete"}
                    </Button>
                    <Button
                      variant="outline"
                      disabled={rowPending}
                      onClick={() => runAction(item.id, { action: "snooze", snooze_hours: 24 })}
                    >
                      Snooze 1 day
                    </Button>
                    <Button
                      variant="outline"
                      disabled={rowPending}
                      onClick={() => runAction(item.id, { action: "snooze", snooze_hours: 72 })}
                    >
                      Snooze 3 days
                    </Button>
                  </div>
                </article>
              );
            })}
          </div>
        </section>

        <section className="space-y-6">
          {selectedLead ? (
            <LeadMemoryPanel
              lead={selectedLead}
              noteDraft={noteDraft}
              onNoteDraftChange={setNoteDraft}
              onSaveNote={saveNote}
              isSavingNote={pendingId === selectedLead.id && isPending}
            />
          ) : null}
          <AIIntakePanel
            advancedAiUnlocked={advancedAiUnlocked}
            billingStatus={initialBilling?.subscription_status ?? null}
            aiPromptDraft={aiPromptDraft}
            aiFormatsDraft={aiFormatsDraft}
            onAiPromptDraftChange={setAiPromptDraft}
            onAiFormatsDraftChange={setAiFormatsDraft}
            onSave={saveAiImportSettings}
            saveStatus={aiSettingsStatus}
            isSaving={isAiSettingsPending}
            canPersistSettings={Boolean(settings)}
          />
          <RemoteImageCapturePanel
            intakeChannel={initialIntakeChannel}
            advancedAiUnlocked={advancedAiUnlocked}
            preferredChannels={initialSettings?.crm_image_intake_channels ?? []}
            routingNotes={initialSettings?.crm_image_intake_notes ?? ""}
          />
          <section className="rounded-[1.75rem] border bg-slate-950 p-6 text-slate-50 shadow-[0_24px_90px_-55px_rgba(15,23,42,0.9)]">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-300">Why This Slice</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight">Relationship memory matters.</h2>
            <ul className="mt-5 space-y-3 text-sm leading-6 text-slate-300">
              <li>Consultants and small agencies already keep their pipeline in spreadsheets, so import removes the adoption cliff.</li>
              <li>A timeline turns the CRM into an operating memory instead of a static record.</li>
              <li>This keeps the wedge narrow: faster follow-up, cleaner handoffs, and less spreadsheet sprawl.</li>
            </ul>
          </section>
        </section>
      </section>
    </>
  );
}

function RemoteImageCapturePanel({
  intakeChannel,
  advancedAiUnlocked,
  preferredChannels,
  routingNotes,
}: {
  intakeChannel: CRMRemoteIntakeChannel | null;
  advancedAiUnlocked: boolean;
  preferredChannels: string[];
  routingNotes: string;
}) {
  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Remote Note Capture</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">Send note photos from your phone.</h2>
      <p className="mt-3 text-sm leading-6 text-slate-600">
        Uploading inside Brivoly is great, but operators often snap notes on the move. Telegram is the first remote
        intake channel because it is already wired into the product and can drop images straight into your account.
      </p>

      {!advancedAiUnlocked ? (
        <div className="mt-5 rounded-[1.3rem] border border-amber-200 bg-amber-50 px-4 py-4 text-sm leading-6 text-amber-900">
          Remote image intake uses the same paid AI gate as advanced spreadsheet and file interpretation.
        </div>
      ) : null}

      <div className="mt-5 rounded-[1.3rem] border bg-slate-50 px-4 py-4">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Current channel</p>
        <p className="mt-2 text-sm font-medium text-slate-900">
          {intakeChannel?.telegram_available ? "Telegram is live for remote note images." : "Remote note capture is not configured yet."}
        </p>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          {intakeChannel?.instructions ?? "Set the CRM intake secret and Telegram bot config to enable phone-first note capture."}
        </p>
        {preferredChannels.length ? (
          <p className="mt-3 text-sm text-slate-700">
            Preferred channels for this account: <span className="font-medium">{preferredChannels.join(", ")}</span>
          </p>
        ) : null}
        {routingNotes ? <p className="mt-2 text-sm leading-6 text-slate-600">{routingNotes}</p> : null}
        {intakeChannel?.intake_caption ? (
          <>
            <p className="mt-4 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Caption to send with the image</p>
            <code className="mt-2 block overflow-x-auto rounded-2xl border bg-white px-4 py-3 text-sm text-slate-900">
              {intakeChannel.intake_caption}
            </code>
            <p className="mt-3 text-xs text-slate-500">
              Send a photo or image document to the bot with that exact caption. Brivoly will import the note into your CRM queue and reply with the result.
            </p>
          </>
        ) : null}
      </div>
    </section>
  );
}

function AIIntakePanel({
  advancedAiUnlocked,
  billingStatus,
  aiPromptDraft,
  aiFormatsDraft,
  onAiPromptDraftChange,
  onAiFormatsDraftChange,
  onSave,
  saveStatus,
  isSaving,
  canPersistSettings,
}: {
  advancedAiUnlocked: boolean;
  billingStatus: string | null;
  aiPromptDraft: string;
  aiFormatsDraft: string;
  onAiPromptDraftChange: (value: string) => void;
  onAiFormatsDraftChange: (value: string) => void;
  onSave: () => void;
  saveStatus: string | null;
  isSaving: boolean;
  canPersistSettings: boolean;
}) {
  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">AI Intake Profile</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">Teach Brivoly your messy files.</h2>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            Store a custom prompt and common source formats per user so future AI-assisted spreadsheet, file, and image interpretation can stay close to how that team actually works.
          </p>
        </div>
        <div className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] ${advancedAiUnlocked ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-amber-200 bg-amber-50 text-amber-800"}`}>
          {advancedAiUnlocked ? "Advanced AI unlocked" : "Advanced AI paywalled"}
        </div>
      </div>

      {!advancedAiUnlocked ? (
        <div className="mt-5 rounded-[1.3rem] border border-amber-200 bg-amber-50 px-4 py-4 text-sm leading-6 text-amber-900">
          AI-assisted file, spreadsheet, and image interpretation should stay behind a paid plan. Current billing status: {formatBillingStatusLabel(billingStatus)}.
        </div>
      ) : null}

      <div className="mt-5 space-y-4">
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Common import formats</span>
          <input
            value={aiFormatsDraft}
            onChange={(event) => onAiFormatsDraftChange(event.target.value)}
            placeholder="csv, google_sheets, spreadsheet_screenshot, pdf_export"
            className="mt-2 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400 focus:bg-white"
          />
        </label>
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Custom AI intake prompt</span>
          <textarea
            value={aiPromptDraft}
            onChange={(event) => onAiPromptDraftChange(event.target.value)}
            rows={6}
            className="mt-2 min-h-36 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400 focus:bg-white"
          />
        </label>
      </div>

      <div className="mt-5 flex items-center gap-3">
        <Button onClick={onSave} disabled={isSaving || !canPersistSettings}>
          {isSaving ? "Saving..." : "Save AI intake profile"}
        </Button>
        {saveStatus ? <p className="text-sm text-slate-500">{saveStatus}</p> : null}
      </div>
      {!canPersistSettings ? <p className="mt-3 text-sm text-slate-500">AI intake settings are unavailable until account settings finish loading.</p> : null}
    </section>
  );
}

function ImportPreviewPanel({
  preview,
  importFieldMapping,
  isImportMappingDirty,
  onFieldMappingChange,
}: {
  preview: CRMImportPreview | null;
  importFieldMapping: Record<string, string>;
  isImportMappingDirty: boolean;
  onFieldMappingChange: (header: string, field: string) => void;
}) {
  if (!preview) {
    return (
      <section className="rounded-[1.4rem] border border-dashed bg-slate-50/70 p-6">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Preview</p>
        <h3 className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">Nothing staged yet.</h3>
        <p className="mt-3 text-sm leading-6 text-slate-600">
          Preview the sheet first to see normalized rows, duplicate detection, and validation issues before importing anything.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-[1.4rem] border bg-slate-950 p-6 text-slate-50 shadow-[0_24px_80px_-55px_rgba(15,23,42,0.9)]">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-300">Preview</p>
      <h3 className="mt-3 text-2xl font-semibold tracking-tight">{preview.source_label} import check</h3>
      <div className="mt-5 grid gap-3 md:grid-cols-3">
        <CompactMetric label="Rows" value={String(preview.total_rows)} />
        <CompactMetric label="Importable" value={String(preview.importable_rows)} />
        <CompactMetric label="Skipped" value={String(preview.duplicate_rows + preview.invalid_rows)} />
      </div>
      <section className="mt-5 rounded-[1.2rem] border border-white/10 bg-white/5 p-4">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Column mapping</p>
            <p className="mt-2 text-sm leading-6 text-slate-300">
              Keep the suggested mapping if it looks right, or correct any column here before importing.
            </p>
          </div>
          {isImportMappingDirty ? <p className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-300">Needs refreshed preview</p> : null}
        </div>
        <div className="mt-4 space-y-3">
          {preview.header_mappings.map((item) => (
            <ImportMappingRow
              key={item.original_header}
              item={item}
              availableFields={preview.available_fields}
              selectedValue={importFieldMapping[item.original_header] ?? ""}
              onChange={onFieldMappingChange}
            />
          ))}
        </div>
      </section>
      <p className="mt-4 text-xs uppercase tracking-[0.18em] text-slate-400">
        Headers · {preview.normalized_headers.join(" · ") || "none detected"}
      </p>
      <div className="mt-5 space-y-3">
        {preview.rows.slice(0, 5).map((row) => (
          <ImportPreviewRowCard key={row.row_number} row={row} />
        ))}
      </div>
      {preview.rows.length > 5 ? <p className="mt-3 text-xs text-slate-400">Showing the first 5 preview rows.</p> : null}
    </section>
  );
}

function ImportMappingRow({
  item,
  availableFields,
  selectedValue,
  onChange,
}: {
  item: CRMImportHeaderMapping;
  availableFields: string[];
  selectedValue: string;
  onChange: (header: string, field: string) => void;
}) {
  return (
    <div className="grid gap-3 rounded-xl border border-white/10 bg-slate-900/40 px-3 py-3 md:grid-cols-[1.1fr_1fr]">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Sheet column</p>
        <p className="mt-1 text-sm font-medium text-white">{item.original_header}</p>
        <p className="mt-2 text-xs text-slate-400">
          Suggested: {item.suggested_field ? formatImportFieldLabel(item.suggested_field) : "Ignore this column"}
        </p>
      </div>
      <label className="block">
        <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Map to</span>
        <select
          value={selectedValue}
          onChange={(event) => onChange(item.original_header, event.target.value)}
          className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-3 text-sm text-white outline-none transition focus:border-slate-400"
        >
          <option value="">Ignore this column</option>
          {availableFields.map((field) => (
            <option key={field} value={field}>
              {formatImportFieldLabel(field)}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}

function ImportPreviewRowCard({ row }: { row: CRMImportPreviewRow }) {
  const hasError = row.issues.some((issue) => issue.severity === "error");
  return (
    <article className={`rounded-[1.2rem] border px-4 py-4 ${hasError ? "border-rose-300 bg-rose-950/40" : row.duplicate ? "border-amber-300 bg-amber-950/30" : "border-white/10 bg-white/5"}`}>
      <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Row {row.row_number}</p>
          <h4 className="mt-2 text-lg font-semibold text-white">{row.lead_name}</h4>
          <p className="text-sm text-slate-300">{row.company_name}</p>
          <p className="mt-2 text-xs uppercase tracking-[0.18em] text-slate-400">Owner · {row.owner_name}</p>
        </div>
        <div className="text-right">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{row.stage}</p>
          <p className="mt-2 text-sm text-slate-200">{formatDateTime(row.next_follow_up_at)}</p>
        </div>
      </div>
      {row.notes ? <p className="mt-3 text-sm leading-6 text-slate-300">{row.notes}</p> : null}
      {row.issues.length ? (
        <div className="mt-3 space-y-2">
          {row.issues.map((issue, index) => (
            <p key={`${issue.row_number}-${issue.field ?? "general"}-${index}`} className={`rounded-xl px-3 py-2 text-xs ${issue.severity === "error" ? "bg-rose-200 text-rose-950" : "bg-amber-200 text-amber-950"}`}>
              {issue.message}
            </p>
          ))}
        </div>
      ) : null}
    </article>
  );
}

function LeadMemoryPanel({
  lead,
  noteDraft,
  onNoteDraftChange,
  onSaveNote,
  isSavingNote,
}: {
  lead: CRMLeadFollowUp;
  noteDraft: string;
  onNoteDraftChange: (value: string) => void;
  onSaveNote: () => void;
  isSavingNote: boolean;
}) {
  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Contact Memory</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">{lead.lead_name}</h2>
      <p className="mt-1 text-sm text-slate-600">{lead.company_name}</p>

      <div className="mt-5 grid gap-3 md:grid-cols-3">
        <TimelineTile label="Current stage" value={lead.stage} />
        <TimelineTile label="Primary channel" value={lead.contact_channel} />
        <TimelineTile label="Owner" value={lead.owner_name} />
      </div>

      <section className="mt-6 rounded-[1.5rem] border bg-slate-50 p-5">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Latest context</p>
        <p className="mt-3 text-sm leading-6 text-slate-700">{lead.notes}</p>
      </section>

      <section className="mt-6 rounded-[1.5rem] border bg-white p-5">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Add internal note</p>
        <textarea
          value={noteDraft}
          onChange={(event) => onNoteDraftChange(event.target.value)}
          placeholder="Capture discovery context, objections, handoff notes, or what changed after the last touch."
          className="mt-3 min-h-28 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400 focus:bg-white"
        />
        <div className="mt-4 flex items-center justify-between gap-4">
          <p className="text-xs text-slate-500">Keep notes lightweight and operational. This is for memory, not prose.</p>
          <Button disabled={isSavingNote || !noteDraft.trim()} onClick={onSaveNote}>
            {isSavingNote ? "Saving..." : "Save note"}
          </Button>
        </div>
      </section>

      <section className="mt-6">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Timeline</p>
        <div className="mt-4 space-y-4">
          {lead.timeline.map((entry) => (
            <div key={entry.id} className="rounded-[1.35rem] border bg-slate-50/80 p-4">
              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
                  {entry.kind.replaceAll("_", " ")} · {entry.channel}
                </p>
                <p className="text-xs text-slate-500">{formatDateTime(entry.occurred_at)}</p>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-700">{entry.summary}</p>
            </div>
          ))}
        </div>
      </section>
    </section>
  );
}

function MetricCard({ label, value, tone }: { label: string; value: string; tone: "neutral" | "warning" | "critical" | "positive" }) {
  const toneClass =
    tone === "positive"
      ? "border-emerald-200 bg-emerald-50 text-emerald-900"
      : tone === "warning"
        ? "border-amber-200 bg-amber-50 text-amber-900"
        : tone === "critical"
          ? "border-rose-200 bg-rose-50 text-rose-900"
          : "border-slate-200 bg-white text-slate-900";

  return (
    <div className={`rounded-[1.4rem] border p-5 shadow-sm ${toneClass}`}>
      <p className="text-xs font-semibold uppercase tracking-[0.2em]">{label}</p>
      <p className="mt-3 text-3xl font-semibold tracking-tight">{value}</p>
    </div>
  );
}

function CompactMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{label}</p>
      <p className="mt-2 text-xl font-semibold text-white">{value}</p>
    </div>
  );
}

function PriorityBadge({ priority }: { priority: string }) {
  const className =
    priority === "high"
      ? "border-rose-200 bg-rose-50 text-rose-700"
      : priority === "medium"
        ? "border-amber-200 bg-amber-50 text-amber-700"
        : "border-slate-200 bg-white text-slate-700";

  return (
    <div className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] ${className}`}>
      {priority} priority
    </div>
  );
}

function TimelineTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border bg-white px-4 py-3">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">{label}</p>
      <p className="mt-2 text-sm text-slate-700">{value}</p>
    </div>
  );
}

function formatDateTime(value: string | null) {
  if (!value) {
    return "Not logged yet";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function formatImportFieldLabel(value: string) {
  return value
    .split("_")
    .map((part) => part.slice(0, 1).toUpperCase() + part.slice(1))
    .join(" ");
}

function hasAdvancedAiAccess(billing: BillingOverview | null) {
  return billing?.enabled === true && ["active", "trialing"].includes(billing.subscription_status ?? "");
}

function formatBillingStatusLabel(status: string | null) {
  if (!status) {
    return "no active subscription";
  }
  return status.replaceAll("_", " ");
}

function isImageFile(fileName: string) {
  const normalized = fileName.toLowerCase();
  return normalized.endsWith(".png") || normalized.endsWith(".jpg") || normalized.endsWith(".jpeg") || normalized.endsWith(".webp");
}
