"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";

import { BusinessProfileOnboarding } from "@/components/settings/business-profile-onboarding";
import { Button } from "@/components/ui/button";
import type {
  AccountSettings,
  BillingOverview,
  CRMEmailDraft,
  CRMFollowUpOverview,
  CRMImportHeaderMapping,
  CRMImportClarificationQuestion,
  CRMImportPreview,
  CRMImportPreviewRow,
  CRMLeadFollowUp,
  CRMPipelineStageSummary,
  CRMRelationshipReminder,
  CRMRemoteIntakeChannel,
} from "@/lib/types";

export type CRMWorkspaceView = "overview" | "followups" | "pipeline" | "import" | "intake";
type CRMIntakeTask = "hub" | "profile" | "routing" | "capture";

export function CRMFollowUpWorkspace({
  initialOverview,
  initialSettings,
  initialBilling,
  initialIntakeChannel,
  view = "overview",
}: {
  initialOverview: CRMFollowUpOverview;
  initialSettings: AccountSettings | null;
  initialBilling: BillingOverview | null;
  initialIntakeChannel: CRMRemoteIntakeChannel | null;
  view?: CRMWorkspaceView;
}) {
  const router = useRouter();
  const pathname = usePathname();
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
  const [clarificationAnswers, setClarificationAnswers] = useState<Record<string, string>>({});
  const [rowOverrides, setRowOverrides] = useState<Record<string, Record<string, string>>>({});
  const [isImportMappingDirty, setIsImportMappingDirty] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [importStatus, setImportStatus] = useState<string | null>(null);
  const [aiPromptDraft, setAiPromptDraft] = useState(initialSettings?.crm_ai_prompt ?? "");
  const [aiFormatsDraft, setAiFormatsDraft] = useState((initialSettings?.crm_preferred_import_formats ?? []).join(", "));
  const [aiSettingsStatus, setAiSettingsStatus] = useState<string | null>(null);
  const [routingChannelsDraft, setRoutingChannelsDraft] = useState((initialSettings?.crm_image_intake_channels ?? []).join(", "));
  const [routingNotesDraft, setRoutingNotesDraft] = useState(initialSettings?.crm_image_intake_notes ?? "");
  const [routingSettingsStatus, setRoutingSettingsStatus] = useState<string | null>(null);
  const [emailObjective, setEmailObjective] = useState<CRMEmailDraft["objective"]>("follow_up");
  const [emailTone, setEmailTone] = useState<CRMEmailDraft["tone"]>("warm");
  const [emailLength, setEmailLength] = useState<CRMEmailDraft["length"]>("short");
  const [emailDraft, setEmailDraft] = useState<CRMEmailDraft | null>(null);
  const [emailSubjectDraft, setEmailSubjectDraft] = useState("");
  const [emailBodyDraft, setEmailBodyDraft] = useState("");
  const [emailStatus, setEmailStatus] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const [isImportPending, startImportTransition] = useTransition();
  const [isAiSettingsPending, startAiSettingsTransition] = useTransition();
  const [isEmailPending, startEmailTransition] = useTransition();

  useEffect(() => {
    if (!selectedLeadId && initialOverview.items[0]) {
      setSelectedLeadId(initialOverview.items[0].id);
    }
  }, [initialOverview.items, selectedLeadId]);

  useEffect(() => {
    setEmailDraft(null);
    setEmailSubjectDraft("");
    setEmailBodyDraft("");
    setEmailStatus(null);
    setEmailObjective("follow_up");
    setEmailTone("warm");
    setEmailLength("short");
  }, [selectedLeadId]);

  const selectedLead = overview.items.find((item) => item.id === selectedLeadId) ?? overview.items[0] ?? null;
  const advancedAiUnlocked = hasAdvancedAiAccess(initialBilling);
  const showingOverview = view === "overview";
  const showingFollowups = view === "followups";
  const showingPipeline = view === "pipeline";
  const showingImport = view === "import";
  const showingIntake = view === "intake";
  const intakeTask = resolveIntakeTask(pathname ?? "/crm/intake");

  useEffect(() => {
    setAiPromptDraft(initialSettings?.crm_ai_prompt ?? "");
    setAiFormatsDraft((initialSettings?.crm_preferred_import_formats ?? []).join(", "));
    setRoutingChannelsDraft((initialSettings?.crm_image_intake_channels ?? []).join(", "));
    setRoutingNotesDraft(initialSettings?.crm_image_intake_notes ?? "");
  }, [initialSettings]);

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

  function buildImportFormData(
    answersOverride?: Record<string, string>,
    mappingOverride?: Record<string, string>,
    rowOverridesOverride?: Record<string, Record<string, string>>,
  ) {
    const formData = new FormData();
    formData.set("source_type", sourceType);
    const effectiveFieldMapping = mappingOverride ?? importFieldMapping;
    if (Object.keys(effectiveFieldMapping).length) {
      formData.set("field_mapping", JSON.stringify(effectiveFieldMapping));
    }
    const effectiveClarificationAnswers = answersOverride ?? clarificationAnswers;
    if (Object.keys(effectiveClarificationAnswers).length) {
      formData.set("clarification_answers", JSON.stringify(effectiveClarificationAnswers));
    }
    const effectiveRowOverrides = rowOverridesOverride ?? rowOverrides;
    if (Object.keys(effectiveRowOverrides).length) {
      formData.set("row_overrides", JSON.stringify(effectiveRowOverrides));
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

  function requestImportPreview(
    answersOverride?: Record<string, string>,
    mappingOverride?: Record<string, string>,
    rowOverridesOverride?: Record<string, Record<string, string>>,
  ) {
    setImportError(null);
    setImportStatus(null);
    startImportTransition(async () => {
      try {
        const data = await requestImportPreviewWithBestEffort(() =>
          buildImportFormData(answersOverride, mappingOverride, rowOverridesOverride),
        );
        setImportPreview(data);
        setImportFieldMapping(
          Object.fromEntries(
            data.header_mappings
              .filter((item) => item.mapped_field)
              .map((item) => [item.original_header, item.mapped_field as string]),
          ),
        );
        setClarificationAnswers((current) => {
          const activeQuestionIds = new Set((data.clarification?.questions ?? []).map((item) => item.id));
          if (!activeQuestionIds.size) {
            return {};
          }
          const nextAnswers = answersOverride ?? current;
          return Object.fromEntries(
            Object.entries(nextAnswers).filter(([key]) => activeQuestionIds.has(key)),
          );
        });
        setRowOverrides((current) =>
          Object.fromEntries(
            Object.entries(rowOverridesOverride ?? current).filter(([rowNumber, fields]) =>
              data.rows.some((row) => String(row.row_number) === rowNumber) && Object.keys(fields).length > 0,
            ),
          ),
        );
        setIsImportMappingDirty(false);
        setImportStatus(
          data.clarification?.required
            ? "AI found a workable draft, but it still needs a couple of quick answers before import is safe."
            : `Preview ready for ${data.importable_rows} importable row${data.importable_rows === 1 ? "" : "s"}.`,
        );
      } catch (previewError) {
        setImportPreview(null);
        setImportError(
          previewError instanceof Error
            ? previewError.message
            : "Brivoly could not build the preview this time, but it kept the import staged so you can try again.",
        );
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
        setClarificationAnswers({});
        setRowOverrides({});
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
    const nextMapping = {
      ...importFieldMapping,
      [header]: field,
    };
    setImportFieldMapping(nextMapping);
    setImportStatus("Re-checking the preview with your updated column mapping...");
    setIsImportMappingDirty(false);
    requestImportPreview(undefined, nextMapping);
  }

  function answerClarificationQuestion(questionId: string, value: string) {
    const nextAnswers = {
      ...clarificationAnswers,
      [questionId]: value,
    };
    setClarificationAnswers(nextAnswers);
    // Clarification answers immediately trigger a fresh preview, so they should not
    // leave the manual-mapping dirty warning visible while that re-check is running.
    setIsImportMappingDirty(false);
    requestImportPreview(nextAnswers);
  }

  function updateRowOverride(rowNumber: number, fieldName: string, value: string) {
    setRowOverrides((current) => ({
      ...current,
      [String(rowNumber)]: {
        ...(current[String(rowNumber)] ?? {}),
        [fieldName]: value,
      },
    }));
    setImportStatus(null);
    setImportError(null);
  }

  function applyRowFix(rowNumber: number) {
    const nextOverrides = {
      ...rowOverrides,
      [String(rowNumber)]: {
        ...(rowOverrides[String(rowNumber)] ?? {}),
      },
    };
    if (!nextOverrides[String(rowNumber)]?.next_follow_up_at?.trim()) {
      setImportError("Enter a next follow-up date before asking Brivoly to re-check that row.");
      return;
    }
    setImportStatus("Re-checking the preview with your in-app row fix...");
    setIsImportMappingDirty(false);
    requestImportPreview(undefined, undefined, nextOverrides);
  }

  async function requestImportPreviewWithBestEffort(buildFormData: () => FormData) {
    let lastMessage = "Brivoly could not build the preview this time, but it kept the import staged so you can try again.";
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const response = await fetch("/api/crm/import/preview", {
        method: "POST",
        body: buildFormData(),
      });
      const data = (await response.json().catch(() => null)) as CRMImportPreview | { error?: string } | null;
      if (response.ok && data && "rows" in data) {
        return data;
      }

      if (data && "error" in data && typeof data.error === "string" && data.error.trim()) {
        lastMessage = data.error.trim();
      } else if (!response.ok && attempt === 0 && response.status >= 500) {
        lastMessage = "Brivoly hit an import hiccup, so it retried the preview automatically. Please try once more if the sheet is still not visible.";
      }
    }
    throw new Error(lastMessage);
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

  function saveIntakeRoutingSettings() {
    if (!settings) {
      return;
    }
    setRoutingSettingsStatus("Saving intake routing preferences...");
    startAiSettingsTransition(async () => {
      const payload: AccountSettings = {
        ...settings,
        crm_image_intake_channels: routingChannelsDraft
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        crm_image_intake_notes: routingNotesDraft.trim(),
      };
      try {
        const response = await fetch("/api/account/settings", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const body = (await response.json().catch(() => null)) as AccountSettings | { error?: string } | null;
        if (!response.ok || !body || !("benchmark" in body)) {
          throw new Error((body && "error" in body && body.error) || "Unable to save intake routing settings.");
        }
        setSettings(body);
        setRoutingChannelsDraft(body.crm_image_intake_channels.join(", "));
        setRoutingNotesDraft(body.crm_image_intake_notes);
        setRoutingSettingsStatus("Intake routing preferences saved.");
      } catch (saveError) {
        setRoutingSettingsStatus(saveError instanceof Error ? saveError.message : "Unable to save intake routing settings.");
      }
    });
  }

  function generateEmailDraft() {
    if (!selectedLead) {
      return;
    }
    setEmailStatus("Designing a follow-up email...");
    startEmailTransition(async () => {
      try {
        const response = await fetch(`/api/crm/followups/${selectedLead.id}/email-draft`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            objective: emailObjective,
            tone: emailTone,
            length: emailLength,
          }),
        });
        const body = (await response.json().catch(() => null)) as CRMEmailDraft | { error?: string } | null;
        if (!response.ok || !body || !("subject" in body)) {
          throw new Error((body && "error" in body && body.error) || "Unable to generate an email draft.");
        }
        setEmailDraft(body);
        setEmailSubjectDraft(body.subject);
        setEmailBodyDraft(body.body);
        setEmailStatus("Draft ready. Tweak anything before sending.");
      } catch (draftError) {
        setEmailStatus(draftError instanceof Error ? draftError.message : "Unable to generate an email draft.");
      }
    });
  }

  return (
    <div className="mt-6">
      <BusinessProfileOnboarding
        initialSettings={settings}
        accent="amber"
        onSettingsUpdated={(nextSettings) => setSettings(nextSettings)}
        title="Set the basics once so Brivoly can sound like your business."
        description="New accounts should quickly tell Brivoly the business name, sender name for automatic emails, and an optional logo. You can skip it for now, but this is how the CRM starts feeling like your workspace instead of a generic tool."
      />

      <CRMViewHeader view={view} />

      <section className="mt-6 grid gap-6 md:grid-cols-4">
        <MetricCard label="Open follow-ups" value={String(overview.total_open)} tone="neutral" />
        <MetricCard label="Due today" value={String(overview.due_today)} tone="warning" />
        <MetricCard label="Overdue" value={String(overview.overdue)} tone={overview.overdue > 0 ? "critical" : "positive"} />
        <MetricCard label="High priority" value={String(overview.high_priority)} tone="neutral" />
      </section>

      {showingOverview && overview.relationship_summary ? (
        <section className="mt-6 grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
          <RelationshipSignalsPanel summary={overview.relationship_summary} />
          <WarmIntroGraphPanel summary={overview.relationship_summary} />
        </section>
      ) : null}

      {showingImport ? (
      <section className="mt-6 rounded-[1.75rem] border bg-white/85 p-6 shadow-sm">
        <div className="grid gap-6 xl:grid-cols-[0.92fr_1.08fr]">
          <section>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Spreadsheet Import</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">Bring your lead sheet in without retyping it.</h2>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              Upload a CSV, XLSX, XLS, or note image, or paste a Google Sheets link. Brivoly normalizes messy headers, flags validation problems, and skips duplicates before anything enters the follow-up queue.
            </p>

            <div className="mt-5 flex flex-wrap gap-3">
              <Button
                variant={sourceType === "file_upload" ? "default" : "outline"}
                onClick={() => {
                  setSourceType("file_upload");
                  setImportPreview(null);
                  setImportFieldMapping({});
                  setClarificationAnswers({});
                  setRowOverrides({});
                  setIsImportMappingDirty(false);
                  setImportStatus(null);
                  setImportError(null);
                }}
              >
                Spreadsheet file
              </Button>
              <Button
                variant={sourceType === "google_sheets" ? "default" : "outline"}
                onClick={() => {
                  setSourceType("google_sheets");
                  setImportPreview(null);
                  setImportFieldMapping({});
                  setClarificationAnswers({});
                  setRowOverrides({});
                  setIsImportMappingDirty(false);
                  setImportStatus(null);
                  setImportError(null);
                }}
              >
                Google Sheets
              </Button>
            </div>

            {sourceType === "file_upload" ? (
              <section className="mt-5 rounded-[1.4rem] border bg-slate-50/80 p-5">
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Spreadsheet file</p>
                <input
                  ref={fileInputRef}
                  type="file"
                  data-testid="crm-import-file-input"
                  accept=".csv,text/csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,.xls,application/vnd.ms-excel,.png,image/png,.jpg,image/jpeg,.jpeg,image/jpeg,.webp,image/webp"
                  className="mt-3 block w-full rounded-2xl border border-dashed border-slate-300 bg-white px-4 py-5 text-sm text-slate-600"
                  onChange={(event) => {
                    setSelectedFile(event.target.files?.[0] ?? null);
                    setImportPreview(null);
                    setImportFieldMapping({});
                    setClarificationAnswers({});
                    setRowOverrides({});
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
                    setClarificationAnswers({});
                    setRowOverrides({});
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
              <Button disabled={isImportPending} onClick={() => requestImportPreview()}>
                {isImportPending ? "Checking..." : importPreview ? "Refresh preview" : "Preview import"}
              </Button>
              <Button
                variant="outline"
                disabled={
                  isImportPending ||
                  !importPreview ||
                  importPreview.importable_rows === 0 ||
                  isImportMappingDirty ||
                  Boolean(importPreview.clarification?.required)
                }
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
          clarificationAnswers={clarificationAnswers}
          rowOverrides={rowOverrides}
          isImportMappingDirty={isImportMappingDirty}
          onFieldMappingChange={updateImportFieldMapping}
          onClarificationAnswer={answerClarificationQuestion}
          onRowOverrideChange={updateRowOverride}
          onApplyRowFix={applyRowFix}
        />
        </div>
      </section>
      ) : null}

      {showingPipeline && overview.pipeline_summary?.stage_summaries?.length ? (
        <div className="mt-6">
          <PipelineBoardPanel
            summary={overview.pipeline_summary.stage_summaries}
            items={overview.items}
            selectedLeadId={selectedLead?.id ?? null}
            onSelectLead={setSelectedLeadId}
          />
        </div>
      ) : null}

      {showingFollowups ? (
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
              settings={settings}
              noteDraft={noteDraft}
              onNoteDraftChange={setNoteDraft}
              onSaveNote={saveNote}
              isSavingNote={pendingId === selectedLead.id && isPending}
              emailObjective={emailObjective}
              emailTone={emailTone}
              emailLength={emailLength}
              emailDraft={emailDraft}
              emailSubjectDraft={emailSubjectDraft}
              emailBodyDraft={emailBodyDraft}
              emailStatus={emailStatus}
              isGeneratingEmail={isEmailPending}
              onEmailObjectiveChange={setEmailObjective}
              onEmailToneChange={setEmailTone}
              onEmailLengthChange={setEmailLength}
              onEmailSubjectDraftChange={setEmailSubjectDraft}
              onEmailBodyDraftChange={setEmailBodyDraft}
              onGenerateEmailDraft={generateEmailDraft}
            />
          ) : null}
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
      ) : null}

      {showingIntake ? (
        <section className="mt-6 space-y-6">
          <IntakeTaskNav activeTask={intakeTask} />
          {intakeTask === "hub" ? (
            <IntakeTaskHub
              advancedAiUnlocked={advancedAiUnlocked}
              preferredChannels={settings?.crm_image_intake_channels ?? []}
              hasMagicLink={Boolean(initialIntakeChannel?.magic_link_url)}
            />
          ) : null}
          {intakeTask === "profile" ? (
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
          ) : null}
          {intakeTask === "routing" ? (
            <IntakeRoutingPanel
              channelsDraft={routingChannelsDraft}
              routingNotesDraft={routingNotesDraft}
              onChannelsDraftChange={setRoutingChannelsDraft}
              onRoutingNotesDraftChange={setRoutingNotesDraft}
              onSave={saveIntakeRoutingSettings}
              saveStatus={routingSettingsStatus}
              isSaving={isAiSettingsPending}
              canPersistSettings={Boolean(settings)}
            />
          ) : null}
          {intakeTask === "capture" ? (
            <RemoteImageCapturePanel
              intakeChannel={initialIntakeChannel}
              advancedAiUnlocked={advancedAiUnlocked}
              preferredChannels={settings?.crm_image_intake_channels ?? []}
              routingNotes={settings?.crm_image_intake_notes ?? ""}
            />
          ) : null}
        </section>
      ) : null}

      {showingOverview ? (
        <section className="mt-6 grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
          <OverviewQuickLinks
            pipelineStages={overview.pipeline_summary?.stage_summaries ?? []}
            selectedLead={selectedLead}
            intakeChannel={initialIntakeChannel}
          />
          <section className="space-y-6">
            {overview.pipeline_summary?.stage_summaries?.length ? (
              <PipelineBoardPanel
                summary={overview.pipeline_summary.stage_summaries}
                items={overview.items.slice(0, 4)}
                selectedLeadId={selectedLead?.id ?? null}
                onSelectLead={setSelectedLeadId}
              />
            ) : null}
          </section>
        </section>
      ) : null}
    </div>
  );
}

function CRMViewHeader({ view }: { view: CRMWorkspaceView }) {
  const copy = {
    overview: {
      eyebrow: "CRM Overview",
      title: "Overview",
      body: "See current CRM activity, pipeline state, and intake status.",
    },
    followups: {
      eyebrow: "Follow-Ups",
      title: "Work the queue with lead memory beside it.",
      body: "This page is for next actions, relationship context, and getting the right follow-up out the door fast.",
    },
    pipeline: {
      eyebrow: "Pipeline",
      title: "See stage pressure across the whole deal flow.",
      body: "Use this page to spot bottlenecks, overdue clusters, and where the pipeline is quietly going stale.",
    },
    import: {
      eyebrow: "Import",
      title: "Bring spreadsheet-held CRM work into Brivoly cleanly.",
      body: "Upload files, preview mappings, fix rows in-app, and commit only after the import looks safe.",
    },
    intake: {
      eyebrow: "Intake",
      title: "Work intake setup as clear, separate jobs.",
      body: "Split intake into AI profile, routing preferences, and remote capture so each setup task has its own place.",
    },
  }[view];

  return (
    <section className="mt-6 rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">{copy.eyebrow}</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">{copy.title}</h2>
      <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-600">{copy.body}</p>
    </section>
  );
}

function resolveIntakeTask(pathname: string): CRMIntakeTask {
  if (pathname === "/crm/intake/profile") {
    return "profile";
  }
  if (pathname === "/crm/intake/routing") {
    return "routing";
  }
  if (pathname === "/crm/intake/capture") {
    return "capture";
  }
  return "hub";
}

function OverviewQuickLinks({
  pipelineStages,
  selectedLead,
  intakeChannel,
}: {
  pipelineStages: CRMPipelineStageSummary[];
  selectedLead: CRMLeadFollowUp | null;
  intakeChannel: CRMRemoteIntakeChannel | null;
}) {
  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Workspace Map</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">Jump straight into the right CRM job.</h2>
      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <QuickLinkCard
          href="/crm/follow-ups"
          title="Follow-Ups"
          body={selectedLead ? `Next lead ready: ${selectedLead.lead_name} at ${selectedLead.company_name}.` : "Work the live follow-up queue and lead memory."}
        />
        <QuickLinkCard
          href="/crm/pipeline"
          title="Pipeline"
          body={pipelineStages.length ? `${pipelineStages.length} active stages are live in the board.` : "See the stage board and pipeline pressure."}
        />
        <QuickLinkCard
          href="/crm/import"
          title="Import"
          body="Bring in spreadsheets, rescue messy headers, and validate rows before commit."
        />
        <QuickLinkCard
          href="/crm/intake"
          title="Intake"
          body={intakeChannel?.magic_link_url ? "Magic-link remote note capture is configured." : "Set up AI intake guidance and remote note capture."}
        />
      </div>
    </section>
  );
}

function QuickLinkCard({ href, title, body }: { href: string; title: string; body: string }) {
  return (
    <Link href={href} className="block rounded-[1.35rem] border bg-slate-50/80 px-5 py-5 transition hover:border-slate-400 hover:bg-white">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{title}</p>
      <p className="mt-3 text-sm leading-6 text-slate-700">{body}</p>
    </Link>
  );
}

function PipelineBoardPanel({
  summary,
  items,
  selectedLeadId,
  onSelectLead,
}: {
  summary: CRMPipelineStageSummary[];
  items: CRMLeadFollowUp[];
  selectedLeadId: string | null;
  onSelectLead: (leadId: string) => void;
}) {
  const itemsByStage = new Map<string, CRMLeadFollowUp[]>();
  for (const item of items) {
    const bucket = itemsByStage.get(item.stage) ?? [];
    bucket.push(item);
    itemsByStage.set(item.stage, bucket);
  }

  return (
      <section className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm xl:col-span-2">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-2xl">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">CRM Pipeline</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">Pipeline</h2>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            Review open leads by stage, urgency, and dormant risk.
          </p>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <CompactMetricLight label="Stages" value={String(summary.length)} tone="neutral" />
          <CompactMetricLight label="Overdue across pipeline" value={String(summary.reduce((total, stage) => total + stage.overdue_count, 0))} tone="warning" />
          <CompactMetricLight label="High priority in flow" value={String(summary.reduce((total, stage) => total + stage.high_priority_count, 0))} tone="critical" />
        </div>
      </div>

      <div className="mt-6 flex gap-4 overflow-x-auto pb-2">
        {summary.map((stage) => {
          const stageItems = itemsByStage.get(stage.stage) ?? [];
          return (
            <section
              key={stage.stage}
              className="min-w-[280px] flex-1 rounded-[1.5rem] border bg-slate-50/80 p-4"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Stage</p>
                  <h3 className="mt-2 text-xl font-semibold tracking-tight text-slate-950">{stage.stage}</h3>
                </div>
                <div className="rounded-full border border-slate-200 bg-white px-3 py-1 text-sm font-semibold text-slate-700">
                  {stage.lead_count}
                </div>
              </div>

              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                <TimelineTile label="Overdue" value={String(stage.overdue_count)} />
                <TimelineTile label="Due in 7 days" value={String(stage.due_this_week_count)} />
                <TimelineTile label="High priority" value={String(stage.high_priority_count)} />
                <TimelineTile label="Dormant" value={String(stage.dormant_count)} />
              </div>

              <div className="mt-4 space-y-3">
                {stageItems.map((item) => {
                  const selected = item.id === selectedLeadId;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => onSelectLead(item.id)}
                      className={`block w-full rounded-[1.2rem] border px-4 py-4 text-left transition ${
                        selected
                          ? "border-slate-900 bg-white shadow-sm"
                          : "border-slate-200 bg-white/85 hover:border-slate-400"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-slate-950">{item.lead_name}</p>
                          <p className="mt-1 text-xs text-slate-500">{item.company_name}</p>
                        </div>
                        <PriorityBadge priority={item.priority} />
                      </div>
                      <p className="mt-3 text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">Next follow-up</p>
                      <p className="mt-1 text-sm text-slate-700">{formatDateTime(item.next_follow_up_at)}</p>
                      <p className="mt-3 text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">Next step</p>
                      <p className="mt-1 text-sm leading-6 text-slate-600">{item.next_step}</p>
                    </button>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
    </section>
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
        Uploading inside Brivoly is great, but operators often snap notes on the move. A signed magic link keeps
        that phone-first capture simple without making people copy a command into Telegram first.
      </p>

      {!advancedAiUnlocked ? (
        <div className="mt-5 rounded-[1.3rem] border border-amber-200 bg-amber-50 px-4 py-4 text-sm leading-6 text-amber-900">
          Remote image intake uses the same paid AI gate as advanced spreadsheet and file interpretation.
        </div>
      ) : null}

      <div className="mt-5 rounded-[1.3rem] border bg-slate-50 px-4 py-4">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Current channel</p>
        <p className="mt-2 text-sm font-medium text-slate-900">
          {intakeChannel?.magic_link_url ? "Magic-link upload is live for remote note images." : "Remote note capture is not configured yet."}
        </p>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          {intakeChannel?.instructions ?? "Set the CRM intake secret to enable phone-first note capture."}
        </p>
        {preferredChannels.length ? (
          <p className="mt-3 text-sm text-slate-700">
            Preferred channels for this account: <span className="font-medium">{preferredChannels.join(", ")}</span>
          </p>
        ) : null}
        {routingNotes ? <p className="mt-2 text-sm leading-6 text-slate-600">{routingNotes}</p> : null}
        {intakeChannel?.magic_link_url ? (
          <>
            <p className="mt-4 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Secure upload link</p>
            <a
              href={intakeChannel.magic_link_url}
              target="_blank"
              rel="noreferrer"
              className="mt-2 block overflow-x-auto rounded-2xl border bg-white px-4 py-3 text-sm text-slate-900 underline decoration-slate-300 underline-offset-4"
            >
              {intakeChannel.magic_link_url}
            </a>
            <p className="mt-3 text-xs text-slate-500">
              Open that link on your phone, upload a photo or screenshot, and Brivoly will import the note into your CRM queue.
            </p>
          </>
        ) : null}
      </div>
    </section>
  );
}

function IntakeTaskNav({ activeTask }: { activeTask: CRMIntakeTask }) {
  const items: Array<{ href: string; title: string; body: string; task: CRMIntakeTask }> = [
    { href: "/crm/intake", title: "Intake Hub", body: "See the overall intake setup.", task: "hub" },
    { href: "/crm/intake/profile", title: "AI Profile", body: "Teach Brivoly your messy sources.", task: "profile" },
    { href: "/crm/intake/routing", title: "Routing", body: "Define preferred channels and notes.", task: "routing" },
    { href: "/crm/intake/capture", title: "Remote Capture", body: "Share the phone upload path.", task: "capture" },
  ];

  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-5 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Intake Tasks</p>
      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {items.map((item) => {
          const active = item.task === activeTask;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`rounded-[1.2rem] border px-4 py-4 transition ${
                active ? "border-slate-900 bg-slate-950 text-white" : "bg-slate-50/80 hover:border-slate-400 hover:bg-white"
              }`}
            >
              <p className={`text-xs font-semibold uppercase tracking-[0.18em] ${active ? "text-cyan-200" : "text-slate-400"}`}>{item.title}</p>
              <p className={`mt-2 text-sm leading-6 ${active ? "text-slate-100" : "text-slate-700"}`}>{item.body}</p>
            </Link>
          );
        })}
      </div>
    </section>
  );
}

function IntakeTaskHub({
  advancedAiUnlocked,
  preferredChannels,
  hasMagicLink,
}: {
  advancedAiUnlocked: boolean;
  preferredChannels: string[];
  hasMagicLink: boolean;
}) {
  return (
    <section className="grid gap-6 xl:grid-cols-3">
      <TaskSummaryCard
        href="/crm/intake/profile"
        eyebrow="Task 1"
        title="Set the AI profile"
        body={advancedAiUnlocked ? "Your paid AI intake tools are available. Keep the prompt and common formats current." : "Unlock the paid AI intake layer before relying on note-image and messy-file interpretation."}
      />
      <TaskSummaryCard
        href="/crm/intake/routing"
        eyebrow="Task 2"
        title="Define routing rules"
        body={preferredChannels.length ? `Preferred channels are set: ${preferredChannels.join(", ")}.` : "Add preferred intake channels and operator notes so the team knows where raw material should come from."}
      />
      <TaskSummaryCard
        href="/crm/intake/capture"
        eyebrow="Task 3"
        title="Share remote capture"
        body={hasMagicLink ? "A signed phone upload link is live and ready to share with operators." : "Finish setup so the remote upload path can be used from a phone."}
      />
    </section>
  );
}

function TaskSummaryCard({
  href,
  eyebrow,
  title,
  body,
}: {
  href: string;
  eyebrow: string;
  title: string;
  body: string;
}) {
  return (
    <Link href={href} className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm transition hover:border-slate-400 hover:bg-white">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">{eyebrow}</p>
      <h3 className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">{title}</h3>
      <p className="mt-3 text-sm leading-6 text-slate-600">{body}</p>
    </Link>
  );
}

function IntakeRoutingPanel({
  channelsDraft,
  routingNotesDraft,
  onChannelsDraftChange,
  onRoutingNotesDraftChange,
  onSave,
  saveStatus,
  isSaving,
  canPersistSettings,
}: {
  channelsDraft: string;
  routingNotesDraft: string;
  onChannelsDraftChange: (value: string) => void;
  onRoutingNotesDraftChange: (value: string) => void;
  onSave: () => void;
  saveStatus: string | null;
  isSaving: boolean;
  canPersistSettings: boolean;
}) {
  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Intake Routing</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">Tell the team how raw intake should arrive.</h2>
      <p className="mt-3 text-sm leading-6 text-slate-600">
        Use this task to define preferred image-intake channels and the operator notes that explain when each path should be used.
      </p>

      <div className="mt-5 space-y-4">
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Preferred channels</span>
          <input
            value={channelsDraft}
            onChange={(event) => onChannelsDraftChange(event.target.value)}
            placeholder="upload, whatsapp, email"
            className="mt-2 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400 focus:bg-white"
          />
        </label>
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Routing notes</span>
          <textarea
            value={routingNotesDraft}
            onChange={(event) => onRoutingNotesDraftChange(event.target.value)}
            rows={6}
            className="mt-2 min-h-36 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400 focus:bg-white"
          />
        </label>
      </div>

      <div className="mt-5 flex items-center gap-3">
        <Button onClick={onSave} disabled={isSaving || !canPersistSettings}>
          {isSaving ? "Saving..." : "Save intake routing"}
        </Button>
        {saveStatus ? <p className="text-sm text-slate-500">{saveStatus}</p> : null}
      </div>
      {!canPersistSettings ? <p className="mt-3 text-sm text-slate-500">Routing settings are unavailable until account settings finish loading.</p> : null}
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
  clarificationAnswers,
  rowOverrides,
  isImportMappingDirty,
  onFieldMappingChange,
  onClarificationAnswer,
  onRowOverrideChange,
  onApplyRowFix,
}: {
  preview: CRMImportPreview | null;
  importFieldMapping: Record<string, string>;
  clarificationAnswers: Record<string, string>;
  rowOverrides: Record<string, Record<string, string>>;
  isImportMappingDirty: boolean;
  onFieldMappingChange: (header: string, field: string) => void;
  onClarificationAnswer: (questionId: string, value: string) => void;
  onRowOverrideChange: (rowNumber: number, fieldName: string, value: string) => void;
  onApplyRowFix: (rowNumber: number) => void;
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

  const clarificationQuestions = preview.clarification?.questions ?? [];
  const nextClarificationQuestion =
    clarificationQuestions.find((question) => !clarificationAnswers[question.id]) ?? clarificationQuestions[0] ?? null;
  const answeredClarificationCount = clarificationQuestions.filter((question) => Boolean(clarificationAnswers[question.id])).length;

  return (
    <section className="rounded-[1.4rem] border bg-slate-950 p-6 text-slate-50 shadow-[0_24px_80px_-55px_rgba(15,23,42,0.9)]">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-300">Preview</p>
      <h3 className="mt-3 text-2xl font-semibold tracking-tight">{preview.source_label} import check</h3>
      <div className="mt-5 grid gap-3 md:grid-cols-3">
        <CompactMetric label="Rows" value={String(preview.total_rows)} />
        <CompactMetric label="Importable" value={String(preview.importable_rows)} />
        <CompactMetric label="Skipped" value={String(preview.duplicate_rows + preview.invalid_rows)} />
      </div>
      {preview.clarification ? (
        <section className={`mt-5 rounded-[1.2rem] border p-4 ${preview.clarification.required ? "border-cyan-300/40 bg-cyan-400/10" : "border-white/10 bg-white/5"}`}>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-200">AI clarification</p>
          <p className="mt-2 text-sm leading-6 text-slate-200">{preview.clarification.assistant_message}</p>
          {preview.clarification.required ? (
            <p className="mt-2 text-xs text-cyan-100/80">
              Brivoly will walk through the remaining ambiguity one question at a time and re-check the sheet after each answer.
            </p>
          ) : null}
          {nextClarificationQuestion ? (
            <div className="mt-4 space-y-4">
              {clarificationQuestions.length > 1 ? (
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-100/80">
                  Question {Math.min(answeredClarificationCount + 1, clarificationQuestions.length)} of {clarificationQuestions.length}
                </p>
              ) : null}
              <ClarificationQuestionCard
                question={nextClarificationQuestion}
                selectedValue={clarificationAnswers[nextClarificationQuestion.id] ?? ""}
                onAnswer={onClarificationAnswer}
              />
              {answeredClarificationCount > 0 ? (
                <div className="rounded-xl border border-white/10 bg-slate-900/30 px-3 py-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Already clarified</p>
                  <div className="mt-2 space-y-2">
                    {clarificationQuestions
                      .filter((question) => Boolean(clarificationAnswers[question.id]))
                      .map((question) => {
                        const answeredChoice = question.choices.find((choice) => choice.value === clarificationAnswers[question.id]);
                        return (
                          <p key={question.id} className="text-sm text-slate-300">
                            <span className="font-medium text-white">{question.prompt}</span>
                            {" · "}
                            {answeredChoice?.label ?? clarificationAnswers[question.id]}
                          </p>
                        );
                      })}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
        </section>
      ) : null}
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
          <ImportPreviewRowCard
            key={row.row_number}
            row={row}
            rowOverride={rowOverrides[String(row.row_number)]}
            onRowOverrideChange={onRowOverrideChange}
            onApplyRowFix={onApplyRowFix}
          />
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

function ClarificationQuestionCard({
  question,
  selectedValue,
  onAnswer,
}: {
  question: CRMImportClarificationQuestion;
  selectedValue: string;
  onAnswer: (questionId: string, value: string) => void;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-slate-900/40 px-3 py-3">
      <p className="text-sm font-medium text-white">{question.prompt}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {question.choices.map((choice) => {
          const selected = choice.value === selectedValue;
          return (
            <button
              key={choice.value}
              type="button"
              onClick={() => onAnswer(question.id, choice.value)}
              className={`rounded-full border px-3 py-2 text-sm transition ${
                selected
                  ? "border-cyan-300 bg-cyan-200 text-slate-950"
                  : "border-slate-700 bg-slate-950 text-slate-100 hover:border-slate-500"
              }`}
            >
              {choice.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ImportPreviewRowCard({
  row,
  rowOverride,
  onRowOverrideChange,
  onApplyRowFix,
}: {
  row: CRMImportPreviewRow;
  rowOverride?: Record<string, string>;
  onRowOverrideChange: (rowNumber: number, fieldName: string, value: string) => void;
  onApplyRowFix: (rowNumber: number) => void;
}) {
  const hasError = row.issues.some((issue) => issue.severity === "error");
  const needsFollowUpFix = row.issues.some((issue) => issue.field === "next_follow_up_at" && issue.severity === "error");
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
      <div className="mt-3 grid gap-3 md:grid-cols-3">
        <TimelineTileDark label="Priority" value={row.priority ? `${row.priority} priority` : "Auto after import"} />
        <TimelineTileDark label="Channel" value={row.contact_channel || "Spreadsheet default"} />
        <TimelineTileDark label="Next step" value={row.next_step || "Brivoly will draft a default follow-up task"} />
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
      {needsFollowUpFix ? (
        <div className="mt-4 rounded-xl border border-cyan-300/30 bg-cyan-400/10 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-200">Fix missing data in Brivoly</p>
          <div className="mt-3 flex flex-col gap-3 md:flex-row md:items-end">
            <label className="block flex-1">
              <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-300">Next follow-up date</span>
              <input
                type="datetime-local"
                value={rowOverride?.next_follow_up_at ?? formatDateTimeInputValue(row.next_follow_up_at)}
                onChange={(event) => onRowOverrideChange(row.row_number, "next_follow_up_at", event.target.value)}
                className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-3 text-sm text-white outline-none transition focus:border-slate-400"
              />
            </label>
            <Button variant="outline" onClick={() => onApplyRowFix(row.row_number)}>
              Re-check row
            </Button>
          </div>
        </div>
      ) : null}
    </article>
  );
}

function LeadMemoryPanel({
  lead,
  settings,
  noteDraft,
  onNoteDraftChange,
  onSaveNote,
  isSavingNote,
  emailObjective,
  emailTone,
  emailLength,
  emailDraft,
  emailSubjectDraft,
  emailBodyDraft,
  emailStatus,
  isGeneratingEmail,
  onEmailObjectiveChange,
  onEmailToneChange,
  onEmailLengthChange,
  onEmailSubjectDraftChange,
  onEmailBodyDraftChange,
  onGenerateEmailDraft,
}: {
  lead: CRMLeadFollowUp;
  settings: AccountSettings | null;
  noteDraft: string;
  onNoteDraftChange: (value: string) => void;
  onSaveNote: () => void;
  isSavingNote: boolean;
  emailObjective: CRMEmailDraft["objective"];
  emailTone: CRMEmailDraft["tone"];
  emailLength: CRMEmailDraft["length"];
  emailDraft: CRMEmailDraft | null;
  emailSubjectDraft: string;
  emailBodyDraft: string;
  emailStatus: string | null;
  isGeneratingEmail: boolean;
  onEmailObjectiveChange: (value: CRMEmailDraft["objective"]) => void;
  onEmailToneChange: (value: CRMEmailDraft["tone"]) => void;
  onEmailLengthChange: (value: CRMEmailDraft["length"]) => void;
  onEmailSubjectDraftChange: (value: string) => void;
  onEmailBodyDraftChange: (value: string) => void;
  onGenerateEmailDraft: () => void;
}) {
  const launchHref = buildMailtoHref(emailSubjectDraft, emailBodyDraft);
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

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <TimelineTile label="Last meaningful interaction" value={formatDateTime(lead.last_meaningful_interaction_at)} />
        <TimelineTile label="Relationship health" value={`${lead.relationship_health_score}/100 · ${formatHealthLabel(lead.relationship_health_label)}`} />
        <TimelineTile label="Dormant detection" value={lead.dormant ? "Dormant and needs a real touch" : "Still active"} />
      </div>

      {lead.referral_source_name || lead.birthday || lead.company_milestone_date || lead.relationship_reminders.length ? (
        <section className="mt-6 rounded-[1.5rem] border bg-amber-50/70 p-5">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-amber-700">Relationship Signals</p>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <TimelineTile label="Warm intro source" value={lead.referral_source_name || "No warm intro mapped yet"} />
            <TimelineTile
              label="Next milestone"
              value={
                lead.company_milestone_date
                  ? `${lead.company_milestone_name || "Company milestone"} · ${formatDateOnly(lead.company_milestone_date)}`
                  : lead.birthday
                    ? `Birthday · ${formatDateOnly(lead.birthday)}`
                    : "No milestone captured yet"
              }
            />
          </div>
          {lead.relationship_reminders.length ? (
            <div className="mt-4 space-y-3">
              {lead.relationship_reminders.map((reminder) => (
                <RelationshipReminderCard key={`${reminder.kind}-${reminder.title}-${reminder.due_at ?? "none"}`} reminder={reminder} />
              ))}
            </div>
          ) : null}
        </section>
      ) : null}

      <section className="mt-6 rounded-[1.5rem] border bg-slate-50 p-5">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Latest context</p>
        <p className="mt-3 text-sm leading-6 text-slate-700">{lead.notes}</p>
      </section>

      <section className="mt-6 rounded-[1.5rem] border bg-white p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Auto Email Designer</p>
            <h3 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">Draft the next follow-up without starting from zero.</h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              Brivoly uses the lead stage, next step, and your saved business profile to draft a follow-up you can edit before sending.
            </p>
          </div>
          <div className="rounded-[1.2rem] border bg-slate-50 px-4 py-3 text-sm text-slate-600 lg:max-w-xs">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Brand source</p>
            <p className="mt-2">
              Sender: <span className="font-medium text-slate-900">{settings?.outbound_sender_name || settings?.business_name || "Fallback defaults"}</span>
            </p>
          </div>
        </div>

        <div className="mt-5 grid gap-4 md:grid-cols-3">
          <label className="block">
            <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Objective</span>
            <select
              value={emailObjective}
              onChange={(event) => onEmailObjectiveChange(event.target.value as CRMEmailDraft["objective"])}
              className="mt-2 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400 focus:bg-white"
            >
              <option value="follow_up">General follow-up</option>
              <option value="recap">Send recap</option>
              <option value="revive">Revive the thread</option>
              <option value="close_loop">Close the loop</option>
            </select>
          </label>
          <label className="block">
            <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Tone</span>
            <select
              value={emailTone}
              onChange={(event) => onEmailToneChange(event.target.value as CRMEmailDraft["tone"])}
              className="mt-2 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400 focus:bg-white"
            >
              <option value="warm">Warm</option>
              <option value="direct">Direct</option>
              <option value="confident">Confident</option>
            </select>
          </label>
          <label className="block">
            <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Length</span>
            <select
              value={emailLength}
              onChange={(event) => onEmailLengthChange(event.target.value as CRMEmailDraft["length"])}
              className="mt-2 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400 focus:bg-white"
            >
              <option value="short">Short</option>
              <option value="medium">Medium</option>
            </select>
          </label>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <Button onClick={onGenerateEmailDraft} disabled={isGeneratingEmail}>
            {isGeneratingEmail ? "Designing..." : emailDraft ? "Redesign draft" : "Design email"}
          </Button>
          {launchHref ? (
            <a
              href={launchHref}
              className="inline-flex items-center rounded-full border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-slate-500 hover:text-slate-950"
            >
              Open in email app
            </a>
          ) : null}
          {emailStatus ? <p className="text-sm text-slate-500">{emailStatus}</p> : null}
        </div>

        {emailDraft ? (
          <>
            <div className="mt-5 rounded-[1.4rem] border bg-slate-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Why this draft</p>
              <div className="mt-3 space-y-2">
                {emailDraft.rationale.map((item) => (
                  <p key={item} className="text-sm leading-6 text-slate-700">
                    {item}
                  </p>
                ))}
              </div>
            </div>
            <label className="mt-5 block">
              <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Subject</span>
              <input
                value={emailSubjectDraft}
                onChange={(event) => onEmailSubjectDraftChange(event.target.value)}
                className="mt-2 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400 focus:bg-white"
              />
            </label>
            <label className="mt-4 block">
              <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Body</span>
              <textarea
                value={emailBodyDraft}
                onChange={(event) => onEmailBodyDraftChange(event.target.value)}
                rows={12}
                className="mt-2 min-h-56 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 font-mono text-sm text-slate-800 outline-none transition focus:border-slate-400 focus:bg-white"
              />
            </label>
          </>
        ) : null}
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

function RelationshipSignalsPanel({ summary }: { summary: NonNullable<CRMFollowUpOverview["relationship_summary"]> }) {
  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Relationship Intelligence</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">See who is slipping, not just who is due.</h2>
      <div className="mt-5 grid gap-3 md:grid-cols-3">
        <CompactMetricLight label="Healthy" value={String(summary.healthy_count)} tone="positive" />
        <CompactMetricLight label="Watch" value={String(summary.watch_count)} tone="warning" />
        <CompactMetricLight label="At risk" value={String(summary.at_risk_count)} tone="critical" />
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <TimelineTile label="Dormant clients" value={String(summary.dormant_count)} />
        <TimelineTile label="Referral reminders" value={String(summary.referral_reminder_count)} />
        <TimelineTile label="Birthday + milestone reminders" value={String(summary.milestone_reminder_count)} />
      </div>
    </section>
  );
}

function WarmIntroGraphPanel({ summary }: { summary: NonNullable<CRMFollowUpOverview["relationship_summary"]> }) {
  return (
    <section className="rounded-[1.75rem] border bg-slate-950 p-6 text-slate-50 shadow-[0_24px_80px_-55px_rgba(15,23,42,0.9)]">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-300">Warm Intro Graph</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight">Keep track of who can reopen a thread.</h2>
      <p className="mt-3 text-sm leading-6 text-slate-300">
        Brivoly maps referral-backed relationships so follow-up pressure can turn into a warmer path instead of another cold nudge.
      </p>
      <div className="mt-5 space-y-3">
        {summary.warm_intro_connections.length ? (
          summary.warm_intro_connections.map((connection) => (
            <div key={`${connection.source_name}-${connection.target_lead_id}`} className="rounded-[1.2rem] border border-white/10 bg-white/5 px-4 py-4">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-200">{connection.source_name}</p>
              <p className="mt-2 text-sm text-slate-200">
                can reopen <span className="font-medium text-white">{connection.target_lead_name}</span> at {connection.target_company_name}
              </p>
              <p className="mt-2 text-xs text-slate-400">Owner: {connection.owner_name}</p>
            </div>
          ))
        ) : (
          <div className="rounded-[1.2rem] border border-dashed border-white/10 bg-white/5 px-4 py-4 text-sm text-slate-300">
            No warm intro links are mapped yet. Capture referral sources on leads so Brivoly can turn them into usable paths.
          </div>
        )}
      </div>
    </section>
  );
}

function RelationshipReminderCard({ reminder }: { reminder: CRMRelationshipReminder }) {
  return (
    <div className="rounded-[1.2rem] border border-amber-200 bg-white/80 px-4 py-4">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-700">{formatReminderKind(reminder.kind)}</p>
        <p className="text-xs text-slate-500">{reminder.due_at ? formatDateTime(reminder.due_at) : "No due time set"}</p>
      </div>
      <p className="mt-2 text-sm font-medium text-slate-900">{reminder.title}</p>
      <p className="mt-2 text-sm leading-6 text-slate-700">{reminder.message}</p>
    </div>
  );
}

function buildMailtoHref(subject: string, body: string) {
  if (!subject.trim() && !body.trim()) {
    return null;
  }
  const recipientHint = "";
  const params: string[] = [];
  if (subject.trim()) {
    params.push(`subject=${encodeURIComponent(subject.trim())}`);
  }
  if (body.trim()) {
    params.push(`body=${encodeURIComponent(body.trim())}`);
  }
  return `mailto:${recipientHint}?${params.join("&")}`;
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

function CompactMetricLight({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "positive" | "warning" | "critical" | "neutral";
}) {
  const className =
    tone === "positive"
      ? "border-emerald-200 bg-emerald-50 text-emerald-900"
      : tone === "warning"
        ? "border-amber-200 bg-amber-50 text-amber-900"
        : tone === "critical"
          ? "border-rose-200 bg-rose-50 text-rose-900"
          : "border-slate-200 bg-white text-slate-900";
  return (
    <div className={`rounded-2xl border px-4 py-3 ${className}`}>
      <p className="text-xs font-semibold uppercase tracking-[0.18em]">{label}</p>
      <p className="mt-2 text-xl font-semibold">{value}</p>
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

function TimelineTileDark({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-900/40 px-4 py-3">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">{label}</p>
      <p className="mt-2 text-sm text-slate-200">{value}</p>
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

function formatDateOnly(value: string | null) {
  if (!value) {
    return "Not set";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
  }).format(date);
}

function formatDateTimeInputValue(value: string | null) {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

function formatImportFieldLabel(value: string) {
  return value
    .split("_")
    .map((part) => part.slice(0, 1).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatHealthLabel(value: string) {
  return value.replaceAll("_", " ");
}

function formatReminderKind(value: string) {
  return value.replaceAll("_", " ");
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
