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

export type CRMWorkspaceView = "overview" | "followups" | "inbox" | "pipeline" | "import" | "intake";
type CRMIntakeTask = "hub" | "profile" | "routing" | "capture";
type RelationshipFilter = "all" | "due" | "stale" | "at_risk";
type InboxFilter = "all" | "reply" | "waiting" | "quiet";

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
  const [relationshipQuery, setRelationshipQuery] = useState("");
  const [relationshipFilter, setRelationshipFilter] = useState<RelationshipFilter>("all");
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
  const [inboxThreadId, setInboxThreadId] = useState("");
  const [inboxSource, setInboxSource] = useState("gmail");
  const [inboxDirection, setInboxDirection] = useState<"inbound" | "outbound">("inbound");
  const [inboxCounterpartName, setInboxCounterpartName] = useState("");
  const [inboxCounterpartEmail, setInboxCounterpartEmail] = useState("");
  const [inboxSubject, setInboxSubject] = useState("");
  const [inboxMessageBody, setInboxMessageBody] = useState("");
  const [inboxStatus, setInboxStatus] = useState<string | null>(null);
  const [inboxQuery, setInboxQuery] = useState("");
  const [inboxFilter, setInboxFilter] = useState<InboxFilter>("all");
  const [isPending, startTransition] = useTransition();
  const [isImportPending, startImportTransition] = useTransition();
  const [isAiSettingsPending, startAiSettingsTransition] = useTransition();
  const [isEmailPending, startEmailTransition] = useTransition();
  const [isInboxPending, startInboxTransition] = useTransition();

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

  const filteredFollowUps = overview.items.filter((item) => matchesRelationshipQuery(item, relationshipQuery) && matchesRelationshipFilter(item, relationshipFilter));
  const selectedLead = filteredFollowUps.find((item) => item.id === selectedLeadId) ?? filteredFollowUps[0] ?? null;
  const advancedAiUnlocked = hasAdvancedAiAccess(initialBilling);
  const showingOverview = view === "overview";
  const showingFollowups = view === "followups";
  const showingInbox = view === "inbox";
  const showingPipeline = view === "pipeline";
  const showingImport = view === "import";
  const showingIntake = view === "intake";
  const intakeTask = resolveIntakeTask(pathname ?? "/clientos/intake");

  useEffect(() => {
    setAiPromptDraft(initialSettings?.crm_ai_prompt ?? "");
    setAiFormatsDraft((initialSettings?.crm_preferred_import_formats ?? []).join(", "));
    setRoutingChannelsDraft((initialSettings?.crm_image_intake_channels ?? []).join(", "));
    setRoutingNotesDraft(initialSettings?.crm_image_intake_notes ?? "");
  }, [initialSettings]);

  useEffect(() => {
    if (!filteredFollowUps.some((item) => item.id === selectedLeadId)) {
      setSelectedLeadId(filteredFollowUps[0]?.id ?? null);
    }
  }, [filteredFollowUps, selectedLeadId]);

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
        const response = await fetch(`/api/crm/followups/email-draft/${selectedLead.id}`, {
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

  function syncInboxThread() {
    setInboxStatus("Syncing the email thread into Brivoly...");
    startInboxTransition(async () => {
      try {
        const threadId = inboxThreadId.trim() || `thread-${Date.now()}`;
        const counterpartEmail = inboxCounterpartEmail.trim().toLowerCase();
        if (!counterpartEmail) {
          throw new Error("Add the contact email before syncing the thread.");
        }
        const response = await fetch("/api/crm/inbox/threads", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            source: inboxSource.trim() || "gmail",
            thread_id: threadId,
            messages: [
              {
                message_id: `${threadId}-${Date.now()}`,
                sent_at: new Date().toISOString(),
                direction: inboxDirection,
                from_email:
                  inboxDirection === "inbound"
                    ? counterpartEmail
                    : "owner@brivoly.local",
                from_name:
                  inboxDirection === "inbound"
                    ? inboxCounterpartName.trim()
                    : settings?.outbound_sender_name || settings?.business_name || "Brivoly",
                to_emails:
                  inboxDirection === "inbound"
                    ? ["owner@brivoly.local"]
                    : [counterpartEmail],
                subject: inboxSubject.trim(),
                body_text: inboxMessageBody.trim(),
                snippet: inboxMessageBody.trim().slice(0, 220),
              },
            ],
          }),
        });
        const body = (await response.json().catch(() => null)) as CRMFollowUpOverview | { error?: string } | null;
        if (!response.ok || !body || !("items" in body)) {
          throw new Error((body && "error" in body && body.error) || "Unable to sync the inbox thread.");
        }
        setOverview(body);
        setSelectedLeadId(body.items[0]?.id ?? null);
        setInboxStatus("Thread synced. Brivoly updated the relationship memory and follow-up queue.");
        setInboxThreadId("");
        setInboxCounterpartName("");
        setInboxCounterpartEmail("");
        setInboxSubject("");
        setInboxMessageBody("");
        router.refresh();
      } catch (syncError) {
        setInboxStatus(syncError instanceof Error ? syncError.message : "Unable to sync the inbox thread.");
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
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Context Intake</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">Bring relationship context in without retyping it.</h2>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              Upload a CSV, XLSX, XLS, or note image, or paste a Google Sheets link. Brivoly cleans up messy headers, spots missing context, and keeps only what is ready to support better follow-through.
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
                File upload
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
                Google Sheet
              </Button>
            </div>

            {sourceType === "file_upload" ? (
              <section className="mt-5 rounded-[1.4rem] border bg-slate-50/80 p-5">
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">File upload</p>
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
                  Supported uploads: CSV, XLSX, XLS, PNG, JPG, JPEG, and WEBP. Note images use paid AI intake. Helpful columns include contact, company, owner, current status, next follow-up, and notes.
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
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Google Sheets link</p>
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
                  {isImportPending ? "Checking..." : importPreview ? "Refresh preview" : "Preview context"}
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
                {isImportPending ? "Importing..." : "Keep these rows"}
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
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Relationship Memory</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">Keep context close to the next touch.</h2>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            Search fast, spot quiet relationships, and move the next touch forward without losing the last meaningful interaction.
          </p>
          {error ? <p className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p> : null}
          <div className="mt-5 rounded-[1.4rem] border bg-slate-50/80 p-4">
            <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
              <input
                value={relationshipQuery}
                onChange={(event) => setRelationshipQuery(event.target.value)}
                placeholder="Search client, company, notes, owner, or next step"
                className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400"
              />
              <div className="flex flex-wrap gap-2">
                {[
                  { value: "all", label: "All" },
                  { value: "due", label: "Today" },
                  { value: "stale", label: "Reconnect" },
                  { value: "at_risk", label: "At risk" },
                ].map((item) => (
                  <button
                    key={item.value}
                    type="button"
                    onClick={() => setRelationshipFilter(item.value as RelationshipFilter)}
                    className={`rounded-full border px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] transition ${
                      relationshipFilter === item.value
                        ? "border-slate-900 bg-slate-950 text-white"
                        : "border-slate-200 bg-white text-slate-600 hover:border-slate-400 hover:text-slate-900"
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
            <p className="mt-3 text-xs text-slate-500">
              {filteredFollowUps.length} relationship{filteredFollowUps.length === 1 ? "" : "s"} match this view.
            </p>
          </div>
          <div className="mt-6 space-y-4">
            {filteredFollowUps.map((item) => {
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
                      <div className="flex flex-wrap items-center gap-2">
                        {item.dormant ? <MiniFlag tone="warning" label="Stale" /> : null}
                        {item.relationship_health_label === "at_risk" ? <MiniFlag tone="critical" label="At risk" /> : null}
                        <PriorityBadge priority={item.priority} />
                      </div>
                    </div>
                    <p className="mt-4 text-sm font-medium text-slate-700">Suggested next touch</p>
                    <p className="mt-1 text-sm leading-6 text-slate-600">{item.next_step}</p>
                    <div className="mt-5 grid gap-3 md:grid-cols-2">
                      <TimelineTile label="Last touch" value={formatDateTime(item.last_contacted_at)} />
                      <TimelineTile label="Next reminder" value={formatDateTime(item.next_follow_up_at)} />
                    </div>
                  </button>
                  <div className="mt-5 flex flex-wrap gap-3">
                    <Button disabled={rowPending} onClick={() => runAction(item.id, { action: "complete" })}>
                      {rowPending ? "Updating..." : "Done"}
                    </Button>
                    <Button
                      variant="outline"
                      disabled={rowPending}
                      onClick={() => runAction(item.id, { action: "snooze", snooze_hours: 24 })}
                    >
                      Tomorrow
                    </Button>
                    <Button
                      variant="outline"
                      disabled={rowPending}
                      onClick={() => runAction(item.id, { action: "snooze", snooze_hours: 72 })}
                    >
                      Later this week
                    </Button>
                  </div>
                </article>
              );
            })}
            {!filteredFollowUps.length ? (
              <div className="rounded-[1.5rem] border border-dashed bg-slate-50/70 p-6 text-sm leading-6 text-slate-600">
                No relationships match this search yet. Try a different keyword or filter.
              </div>
            ) : null}
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
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-300">Why Brivoly</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight">Brivoly remembers relationships so freelancers do not have to.</h2>
            <ul className="mt-5 space-y-3 text-sm leading-6 text-slate-300">
              <li>Every note, reminder, and suggested message should lower mental overhead instead of adding admin.</li>
              <li>Brivoly should help you stay warm, responsive, and top-of-mind without more software work.</li>
              <li>The goal is continuity and follow-through, not pipeline management.</li>
            </ul>
          </section>
        </section>
      </section>
      ) : null}

      {showingInbox ? (
        <section className="mt-6 grid gap-6 xl:grid-cols-[0.92fr_1.08fr]">
          <section className="rounded-[1.75rem] border bg-white/85 p-6 shadow-sm">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Inbox Memory</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">Let Brivoly keep relationship context current from email.</h2>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              Brivoly turns email activity into living relationship memory: it matches contacts by email, creates missing contacts automatically, and keeps the right conversation attached to the right person.
            </p>

            <div className="mt-6 grid gap-4 md:grid-cols-3">
              <CompactMetricLight label="Reply soon" value={String(overview.inbox_summary?.needs_reply_count ?? 0)} tone="critical" />
              <CompactMetricLight label="Waiting on them" value={String(overview.inbox_summary?.waiting_on_contact_count ?? 0)} tone="warning" />
              <CompactMetricLight label="Quiet threads" value={String(overview.inbox_summary?.stale_thread_count ?? 0)} tone="neutral" />
            </div>

            <section className="mt-6 rounded-[1.4rem] border bg-slate-50/80 p-5">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Inbox sync preview</p>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                Use this to simulate inbox sync while real provider connections are being wired. The same API route is ready for Gmail- or Outlook-style thread events.
              </p>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <input value={inboxThreadId} onChange={(event) => setInboxThreadId(event.target.value)} placeholder="Thread ID (optional)" className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400" />
                <input value={inboxSource} onChange={(event) => setInboxSource(event.target.value)} placeholder="Source (gmail, outlook, api)" className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400" />
                <input value={inboxCounterpartName} onChange={(event) => setInboxCounterpartName(event.target.value)} placeholder="Contact name" className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400" />
                <input value={inboxCounterpartEmail} onChange={(event) => setInboxCounterpartEmail(event.target.value)} placeholder="contact@client.com" className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400" />
                <input value={inboxSubject} onChange={(event) => setInboxSubject(event.target.value)} placeholder="Thread subject" className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400 md:col-span-2" />
                <div className="flex flex-wrap gap-2 md:col-span-2">
                  {(["inbound", "outbound"] as const).map((item) => (
                    <button
                      key={item}
                      type="button"
                      onClick={() => setInboxDirection(item)}
                      className={`rounded-full border px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] transition ${
                        inboxDirection === item
                          ? "border-slate-900 bg-slate-950 text-white"
                          : "border-slate-200 bg-white text-slate-600 hover:border-slate-400 hover:text-slate-900"
                      }`}
                    >
                      {item === "inbound" ? "Inbound to you" : "Outbound from you"}
                    </button>
                  ))}
                </div>
                <textarea value={inboxMessageBody} onChange={(event) => setInboxMessageBody(event.target.value)} placeholder="Latest email body or key snippet" className="min-h-[150px] w-full rounded-[1.4rem] border border-slate-200 bg-white px-4 py-3 text-sm leading-6 text-slate-800 outline-none transition focus:border-slate-400 md:col-span-2" />
              </div>
              <div className="mt-4 flex flex-wrap gap-3">
                <Button disabled={isInboxPending} onClick={syncInboxThread}>
                  {isInboxPending ? "Syncing..." : "Sync thread"}
                </Button>
              </div>
              {inboxStatus ? <p className="mt-4 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700">{inboxStatus}</p> : null}
            </section>

            {selectedLead ? (
              <InboxNextMovePanel
                lead={selectedLead}
                onDraftReply={() => {
                  setEmailObjective("follow_up");
                  setEmailTone("warm");
                  setEmailLength("short");
                  generateEmailDraft();
                }}
                isDrafting={isEmailPending}
                draftStatus={emailStatus}
              />
            ) : null}
          </section>

          <InboxActivityPanel
            items={overview.items}
            selectedLeadId={selectedLead?.id ?? null}
            onSelectLead={setSelectedLeadId}
            inboxQuery={inboxQuery}
            inboxFilter={inboxFilter}
            onInboxQueryChange={setInboxQuery}
            onInboxFilterChange={setInboxFilter}
          />
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
          <TodayPrioritiesPanel
            items={overview.items}
            selectedLead={selectedLead}
            inboxSummary={overview.inbox_summary}
          />
          {overview.relationship_summary ? <RelationshipContinuityPanel summary={overview.relationship_summary} /> : null}
        </section>
      ) : null}
    </div>
  );
}

function CRMViewHeader({ view }: { view: CRMWorkspaceView }) {
  const copy = {
    overview: {
      eyebrow: "Today",
      title: "Today’s relationship priorities.",
      body: "See who needs your attention, what is slipping, and where a warm follow-through will matter most.",
    },
    followups: {
      eyebrow: "Relationship Memory",
      title: "Never lose track of where a relationship stands.",
      body: "Keep notes, context, and the next touch together so client continuity does not depend on your memory alone.",
    },
    inbox: {
      eyebrow: "Inbox Memory",
      title: "Let email quietly keep relationship memory up to date.",
      body: "Brivoly turns inbox activity into context, summaries, and follow-through without asking you to log everything by hand.",
    },
    pipeline: {
      eyebrow: "Attention",
      title: "See who is slipping before opportunities go cold.",
      body: "Use this page to spot quiet relationships, reopening opportunities, and where a gentle reconnect is due.",
    },
    import: {
      eyebrow: "Context Intake",
      title: "Bring client context into Brivoly without extra cleanup.",
      body: "Upload spreadsheets and raw note images, let Brivoly make sense of them, and only keep what supports better follow-through.",
    },
    intake: {
      eyebrow: "Client Dropzones",
      title: "Make it easy for clients to send context when it matters.",
      body: "Use no-login upload links, light routing rules, and mobile-first capture so updates land where the relationship already lives.",
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
  if (pathname === "/crm/intake/profile" || pathname === "/clientos/intake/profile") {
    return "profile";
  }
  if (pathname === "/crm/intake/routing" || pathname === "/clientos/intake/routing") {
    return "routing";
  }
  if (pathname === "/crm/intake/capture" || pathname === "/clientos/intake/capture") {
    return "capture";
  }
  return "hub";
}

function TodayPrioritiesPanel({
  items,
  selectedLead,
  inboxSummary,
}: {
  items: CRMLeadFollowUp[];
  selectedLead: CRMLeadFollowUp | null;
  inboxSummary: CRMFollowUpOverview["inbox_summary"];
}) {
  const replyLead = items.find((item) => item.recent_email_threads.some((thread) => thread.needs_reply));
  const reconnectLead = items.find((item) => item.dormant || item.relationship_health_label === "at_risk");
  const proposalLead = items.find((item) => isProposalFollowThrough(item));
  const recentContextLead = items.find((item) => getLatestContextEntry(item));

  const priorities = compactPriorityCards([
    replyLead
      ? {
          id: `${replyLead.id}-reply`,
          href: "/clientos/inbox",
          eyebrow: "Reply soon",
          title: `Reply to ${replyLead.lead_name}`,
          body: getReplySummary(replyLead),
          meta: `${replyLead.company_name} · ${formatDateTime(getNewestThreadTime(replyLead) ?? replyLead.next_follow_up_at)}`,
        }
      : null,
    reconnectLead
      ? {
          id: `${reconnectLead.id}-reconnect`,
          href: "/clientos/follow-ups",
          eyebrow: "Reconnect",
          title: `Reconnect with ${reconnectLead.lead_name}`,
          body: reconnectLead.relationship_reminders[0]?.message ?? reconnectLead.next_step,
          meta: `${reconnectLead.company_name} · last meaningful touch ${formatDateTime(reconnectLead.last_meaningful_interaction_at)}`,
        }
      : null,
    proposalLead
      ? {
          id: `${proposalLead.id}-proposal`,
          href: "/clientos/follow-ups",
          eyebrow: "Proposal follow-up",
          title: `Keep momentum with ${proposalLead.lead_name}`,
          body: proposalLead.next_step,
          meta: `${proposalLead.company_name} · ${formatStageLabel(proposalLead.stage)}`,
        }
      : null,
    recentContextLead
      ? {
          id: `${recentContextLead.id}-context`,
          href: "/clientos/follow-ups",
          eyebrow: "Fresh context",
          title: `New context from ${recentContextLead.lead_name}`,
          body: getLatestContextEntry(recentContextLead)?.summary ?? recentContextLead.notes,
          meta: `${recentContextLead.company_name} · ${formatDateTime(getLatestContextEntry(recentContextLead)?.occurred_at ?? null)}`,
        }
      : null,
  ]);

  const fallbackPriorities = items.slice(0, 4).map((item) => ({
    id: item.id,
    href: "/clientos/follow-ups",
    eyebrow: "Next touch",
    title: summarizePriority(item),
    body: item.next_step,
    meta: `${item.lead_name} · ${formatDateTime(item.next_follow_up_at)}`,
  }));
  const visiblePriorities = (priorities.length ? priorities : fallbackPriorities).slice(0, 4);

  const replyCount = inboxSummary?.needs_reply_count ?? 0;
  const reconnectCount = items.filter((item) => item.dormant || item.relationship_health_label === "at_risk").length;
  const proposalCount = items.filter((item) => isProposalFollowThrough(item)).length;

  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Today’s priorities</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">A short list of who needs your attention right now.</h2>
      <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
        Brivoly surfaces the next relationship moves so you can stay responsive without scanning every thread, note, and reminder yourself.
      </p>
      <div className="mt-5 grid gap-3 md:grid-cols-3">
        <TodaySignal
          label="Reply pressure"
          value={replyCount ? `${replyCount} conversation${replyCount === 1 ? "" : "s"} waiting on you` : "No replies piling up"}
        />
        <TodaySignal
          label="Reconnects"
          value={reconnectCount ? `${reconnectCount} relationship${reconnectCount === 1 ? "" : "s"} could cool off` : "No quiet relationships need a nudge"}
        />
        <TodaySignal
          label="Proposal momentum"
          value={proposalCount ? `${proposalCount} proposal${proposalCount === 1 ? "" : "s"} need follow-through` : "No proposals need a push today"}
        />
      </div>
      <div className="mt-5 space-y-3">
        {visiblePriorities.map((item) => (
          <PriorityCard key={item.id} href={item.href} eyebrow={item.eyebrow} title={item.title} body={item.body} meta={item.meta} />
        ))}
      </div>
      <div className="mt-5 grid gap-4 md:grid-cols-3">
        <QuickLinkCard href="/clientos/follow-ups" title="Relationship memory" body="Keep the last touch, the next touch, and the full story together." />
        <QuickLinkCard href="/clientos/inbox" title="Inbox continuity" body="Let email quietly update context instead of asking you to log everything." />
        <QuickLinkCard href="/clientos/intake" title="Client dropzones" body="Let clients send files and notes without friction when something changes." />
      </div>
    </section>
  );
}

function TodaySignal({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.2rem] border bg-slate-50/80 px-4 py-4">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{label}</p>
      <p className="mt-2 text-sm leading-6 text-slate-700">{value}</p>
    </div>
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

function RelationshipContinuityPanel({ summary }: { summary: NonNullable<CRMFollowUpOverview["relationship_summary"]> }) {
  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Relationship continuity</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">Stay warm without holding everything in your head.</h2>
      <div className="mt-5 grid gap-3 md:grid-cols-3">
        <CompactMetricLight label="Steady" value={String(summary.healthy_count)} tone="positive" />
        <CompactMetricLight label="Needs care" value={String(summary.watch_count)} tone="warning" />
        <CompactMetricLight label="Slipping" value={String(summary.dormant_count + summary.at_risk_count)} tone="critical" />
      </div>
      <div className="mt-4 space-y-3">
        <TimelineTile label="Warm re-entry paths" value={`${summary.warm_intro_connections.length} contact${summary.warm_intro_connections.length === 1 ? "" : "s"} could help reopen a thread`} />
        <TimelineTile label="Personal reminders" value={`${summary.referral_reminder_count + summary.milestone_reminder_count} moment${summary.referral_reminder_count + summary.milestone_reminder_count === 1 ? "" : "s"} worth a thoughtful touch`} />
      </div>
    </section>
  );
}

function PriorityCard({
  href,
  eyebrow,
  title,
  body,
  meta,
}: {
  href: string;
  eyebrow: string;
  title: string;
  body: string;
  meta: string;
}) {
  return (
    <Link href={href} className="block rounded-[1.35rem] border bg-slate-50/80 px-5 py-5 transition hover:border-slate-400 hover:bg-white">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{eyebrow}</p>
      <p className="text-lg font-semibold tracking-tight text-slate-950">{title}</p>
      <p className="mt-2 text-sm leading-6 text-slate-600">{body}</p>
      <p className="mt-3 text-xs text-slate-500">{meta}</p>
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
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Where attention is needed</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">See where each relationship stands.</h2>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            Review which relationships feel warm, which need a reconnect, and where momentum is slipping.
          </p>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <CompactMetricLight label="Quiet relationships" value={String(summary.reduce((total, stage) => total + stage.dormant_count, 0))} tone="warning" />
          <CompactMetricLight label="Needs a touch" value={String(summary.reduce((total, stage) => total + stage.overdue_count, 0))} tone="critical" />
          <CompactMetricLight label="Due soon" value={String(summary.reduce((total, stage) => total + stage.due_this_week_count, 0))} tone="neutral" />
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
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Where it stands</p>
                  <h3 className="mt-2 text-xl font-semibold tracking-tight text-slate-950">{stage.stage}</h3>
                </div>
                <div className="rounded-full border border-slate-200 bg-white px-3 py-1 text-sm font-semibold text-slate-700">
                  {stage.lead_count}
                </div>
              </div>

              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                <TimelineTile label="Needs a touch" value={String(stage.overdue_count)} />
                <TimelineTile label="Due soon" value={String(stage.due_this_week_count)} />
                <TimelineTile label="Warm" value={String(stage.high_priority_count)} />
                <TimelineTile label="Quiet" value={String(stage.dormant_count)} />
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
                      <p className="mt-3 text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">Next reminder</p>
                      <p className="mt-1 text-sm text-slate-700">{formatDateTime(item.next_follow_up_at)}</p>
                      <p className="mt-3 text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">Suggested next touch</p>
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

function InboxActivityPanel({
  items,
  selectedLeadId,
  onSelectLead,
  inboxQuery,
  inboxFilter,
  onInboxQueryChange,
  onInboxFilterChange,
}: {
  items: CRMLeadFollowUp[];
  selectedLeadId: string | null;
  onSelectLead: (leadId: string) => void;
  inboxQuery: string;
  inboxFilter: InboxFilter;
  onInboxQueryChange: (value: string) => void;
  onInboxFilterChange: (value: InboxFilter) => void;
}) {
  const threads = items
    .flatMap((item) =>
      item.recent_email_threads.map((thread) => ({
        leadId: item.id,
        leadName: item.lead_name,
        companyName: item.company_name,
        stage: item.stage,
        notes: item.notes,
        nextStep: item.next_step,
        thread,
      })),
    )
    .sort((left, right) => new Date(right.thread.last_message_at).getTime() - new Date(left.thread.last_message_at).getTime());
  const filteredThreads = threads.filter((item) => matchesInboxThread(item, inboxQuery, inboxFilter));

  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Relationship activity</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">Recent conversations Brivoly is keeping warm.</h2>
      <div className="mt-5 rounded-[1.35rem] border bg-slate-50/80 p-4">
        <div className="grid gap-3 lg:grid-cols-[1.2fr_auto] lg:items-center">
          <input
            value={inboxQuery}
            onChange={(event) => onInboxQueryChange(event.target.value)}
            placeholder="Search by name, company, subject, or email"
            className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400"
          />
          <div className="flex flex-wrap gap-2">
            {[
              { value: "all", label: "All" },
              { value: "reply", label: "Reply soon" },
              { value: "waiting", label: "Waiting" },
              { value: "quiet", label: "Quiet" },
            ].map((item) => (
              <button
                key={item.value}
                type="button"
                onClick={() => onInboxFilterChange(item.value as InboxFilter)}
                className={`rounded-full border px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] transition ${
                  inboxFilter === item.value
                    ? "border-slate-900 bg-slate-950 text-white"
                    : "border-slate-200 bg-white text-slate-600 hover:border-slate-400 hover:text-slate-900"
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
        <p className="mt-3 text-xs text-slate-500">
          {filteredThreads.length} conversation{filteredThreads.length === 1 ? "" : "s"} match the current view.
        </p>
      </div>
      <div className="mt-6 space-y-4">
        {filteredThreads.map(({ leadId, leadName, companyName, stage, thread, notes, nextStep }) => {
          const selected = leadId === selectedLeadId;
          return (
            <button
              key={thread.thread_id}
              type="button"
              onClick={() => onSelectLead(leadId)}
              className={`block w-full rounded-[1.35rem] border px-5 py-5 text-left transition ${
                selected ? "border-slate-900 bg-white shadow-sm" : "bg-slate-50/80 hover:border-slate-400 hover:bg-white"
              }`}
            >
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                    {formatStageLabel(stage)} · {thread.last_message_direction === "inbound" ? "Needs your reply" : "Waiting on them"}
                  </p>
                  <h3 className="mt-2 text-xl font-semibold tracking-tight text-slate-950">{thread.subject}</h3>
                  <p className="mt-1 text-sm text-slate-600">
                    {leadName} · {companyName}
                  </p>
                  <p className="mt-3 text-sm leading-6 text-slate-600">{summarizeThreadPulse(thread, nextStep, notes)}</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {thread.needs_reply ? <MiniFlag tone="critical" label="Reply" /> : null}
                  {thread.waiting_on_contact ? <MiniFlag tone="warning" label="Waiting" /> : null}
                  {isQuietThread(thread) ? <MiniFlag tone="neutral" label="Quiet" /> : null}
                  <div className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-slate-600">
                    {thread.message_count} msg
                  </div>
                </div>
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-3">
                <TimelineTile label="Conversation pulse" value={describeThreadState(thread)} />
                <TimelineTile label="Counterpart" value={thread.counterpart_email} />
                <TimelineTile label="Last message" value={formatDateTime(thread.last_message_at)} />
              </div>
            </button>
          );
        })}
        {!filteredThreads.length ? (
          <div className="rounded-[1.35rem] border border-dashed bg-slate-50/70 p-6 text-sm leading-6 text-slate-600">
            No conversations match this view yet. Once inbox sync is flowing, this becomes the quiet memory layer for who said what and who needs a reply.
          </div>
        ) : null}
      </div>
    </section>
  );
}

function InboxNextMovePanel({
  lead,
  onDraftReply,
  isDrafting,
  draftStatus,
}: {
  lead: CRMLeadFollowUp;
  onDraftReply: () => void;
  isDrafting: boolean;
  draftStatus: string | null;
}) {
  const latestThread = [...lead.recent_email_threads].sort(
    (left, right) => new Date(right.last_message_at).getTime() - new Date(left.last_message_at).getTime(),
  )[0] ?? null;

  return (
    <section className="mt-6 rounded-[1.4rem] border bg-white p-5 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Next move</p>
      <h3 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">{lead.lead_name}</h3>
      <p className="mt-1 text-sm text-slate-600">{lead.company_name}</p>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <TimelineTile label="Conversation pulse" value={latestThread ? describeThreadState(latestThread) : "No synced thread yet"} />
        <TimelineTile label="Suggested next touch" value={lead.next_step} />
      </div>
      {latestThread ? (
        <div className="mt-4 rounded-[1.2rem] border bg-slate-50/80 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Latest thread</p>
          <p className="mt-2 text-sm font-medium text-slate-900">{latestThread.subject}</p>
          <p className="mt-2 text-sm leading-6 text-slate-600">{summarizeThreadPulse(latestThread, lead.next_step, lead.notes)}</p>
        </div>
      ) : null}
      <div className="mt-4 flex flex-wrap gap-3">
        <Button disabled={isDrafting} onClick={onDraftReply}>
          {isDrafting ? "Drafting..." : "Draft reply"}
        </Button>
        <Button asChild variant="outline">
          <Link href="/clientos/follow-ups">Open relationship</Link>
        </Button>
      </div>
      {draftStatus ? <p className="mt-4 text-sm text-slate-500">{draftStatus}</p> : null}
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
  const normalizedChannels = normalizeDisplayChannels(preferredChannels);

  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Client Dropzones</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">Share a no-login upload link with clients.</h2>
      <p className="mt-3 text-sm leading-6 text-slate-600">
        Brivoly gives freelancers a simple mobile-first dropzone for files, screenshots, and note images. Clients can upload without logging in, and that context lands back in the relationship timeline.
      </p>

      {!advancedAiUnlocked ? (
        <div className="mt-5 rounded-[1.3rem] border border-amber-200 bg-amber-50 px-4 py-4 text-sm leading-6 text-amber-900">
          Remote image intake uses the same paid AI gate as advanced spreadsheet and file interpretation.
        </div>
      ) : null}

      <div className="mt-5 rounded-[1.3rem] border bg-slate-50 px-4 py-4">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Current channel</p>
        <p className="mt-2 text-sm font-medium text-slate-900">
          {intakeChannel?.magic_link_url ? "No-login client dropzone is live." : "Client dropzone is not configured yet."}
        </p>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          {intakeChannel?.instructions ?? "Set the CRM intake secret to enable phone-first note capture."}
        </p>
        {normalizedChannels.length ? (
          <p className="mt-3 text-sm text-slate-700">
            Preferred channels for this account: <span className="font-medium">{normalizedChannels.join(", ")}</span>
          </p>
        ) : null}
        {routingNotes ? <p className="mt-2 text-sm leading-6 text-slate-600">{routingNotes}</p> : null}
        {intakeChannel?.magic_link_url ? (
          <>
            <p className="mt-4 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Client upload link</p>
            <a
              href={intakeChannel.magic_link_url}
              target="_blank"
              rel="noreferrer"
              className="mt-2 block overflow-x-auto rounded-2xl border bg-white px-4 py-3 text-sm text-slate-900 underline decoration-slate-300 underline-offset-4"
            >
              {intakeChannel.magic_link_url}
            </a>
            <p className="mt-3 text-xs text-slate-500">
              Share that link with a client or open it yourself on mobile. Uploads flow back into Brivoly without requiring a login.
            </p>
          </>
        ) : null}
      </div>
    </section>
  );
}

function IntakeTaskNav({ activeTask }: { activeTask: CRMIntakeTask }) {
  const items: Array<{ href: string; title: string; body: string; task: CRMIntakeTask }> = [
    { href: "/clientos/intake", title: "Dropzone Hub", body: "See the overall intake setup.", task: "hub" },
    { href: "/clientos/intake/profile", title: "AI Profile", body: "Teach Brivoly your messy sources.", task: "profile" },
    { href: "/clientos/intake/routing", title: "Routing", body: "Define preferred channels and notes.", task: "routing" },
    { href: "/clientos/intake/capture", title: "Client Link", body: "Share the no-login upload path.", task: "capture" },
  ];

  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-5 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Dropzone Setup</p>
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
  const normalizedChannels = normalizeDisplayChannels(preferredChannels);

  return (
    <section className="grid gap-6 xl:grid-cols-3">
      <TaskSummaryCard
        href="/clientos/intake/profile"
        eyebrow="Step 1"
        title="Teach Brivoly your source material"
        body={advancedAiUnlocked ? "Your paid AI intake tools are available. Keep the prompt and common formats current." : "Unlock the paid AI intake layer before relying on note-image and messy-file interpretation."}
      />
      <TaskSummaryCard
        href="/clientos/intake/routing"
        eyebrow="Step 2"
        title="Decide how context should arrive"
        body={normalizedChannels.length ? `Preferred channels are set: ${normalizedChannels.join(", ")}.` : "Add preferred intake channels and operator notes so the team knows where raw material should come from."}
      />
      <TaskSummaryCard
        href="/clientos/intake/capture"
        eyebrow="Step 3"
        title="Share the client dropzone"
        body={hasMagicLink ? "A signed no-login upload link is live and ready to share with clients." : "Finish setup so the client upload path can be used from a phone."}
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
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">Decide how relationship context should arrive.</h2>
      <p className="mt-3 text-sm leading-6 text-slate-600">
        Use this task to define the preferred intake paths and the notes that explain when each one should be used.
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

function normalizeDisplayChannels(channels: string[]): string[] {
  return channels.map((channel) => (channel === "telegram" ? "magic_link" : channel));
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
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">Teach Brivoly the context you usually receive.</h2>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            Store a custom prompt and common source formats per user so future AI-assisted spreadsheet, file, and image interpretation stays close to how you actually work.
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
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Relationship Memory</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">{lead.lead_name}</h2>
      <p className="mt-1 text-sm text-slate-600">{lead.company_name}</p>

      <div className="mt-5 grid gap-3 md:grid-cols-3">
        <TimelineTile label="Where it stands" value={formatStageLabel(lead.stage)} />
        <TimelineTile label="Best channel" value={lead.contact_channel} />
        <TimelineTile label="Point person" value={lead.owner_name} />
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <TimelineTile label="Last meaningful interaction" value={formatDateTime(lead.last_meaningful_interaction_at)} />
        <TimelineTile label="Relationship health" value={`${lead.relationship_health_score}/100 · ${formatHealthLabel(lead.relationship_health_label)}`} />
        <TimelineTile label="Dormant detection" value={lead.dormant ? "Dormant and needs a real touch" : "Still active"} />
      </div>

      {lead.referral_source_name || lead.birthday || lead.company_milestone_date || lead.relationship_reminders.length ? (
        <section className="mt-6 rounded-[1.5rem] border bg-amber-50/70 p-5">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-amber-700">Keep this relationship warm</p>
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
        <p className="ui-eyebrow">Latest context</p>
        <p className="mt-3 text-sm leading-6 text-slate-700">{lead.notes}</p>
      </section>

      <section className="mt-6 rounded-[1.5rem] border bg-white p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="ui-eyebrow">Follow-Up Intelligence</p>
            <h3 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">Draft the next reconnect without starting from zero.</h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              Brivoly uses the latest context, suggested next touch, and your saved business profile to suggest a message you can edit before sending.
            </p>
          </div>
          <div className="rounded-[1.2rem] border bg-slate-50 px-4 py-3 text-sm text-slate-600 lg:max-w-xs">
            <p className="ui-eyebrow">Brand source</p>
            <p className="mt-2">
              Sender: <span className="font-medium text-slate-900">{settings?.outbound_sender_name || settings?.business_name || "Fallback defaults"}</span>
            </p>
          </div>
        </div>

        <div className="mt-5 grid gap-4 md:grid-cols-3">
          <label className="block">
            <span className="ui-eyebrow">Objective</span>
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
            <span className="ui-eyebrow">Tone</span>
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
            <span className="ui-eyebrow">Length</span>
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
              <p className="ui-eyebrow">Why this draft</p>
              <div className="mt-3 space-y-2">
                {emailDraft.rationale.map((item) => (
                  <p key={item} className="text-sm leading-6 text-slate-700">
                    {item}
                  </p>
                ))}
              </div>
            </div>
            <label className="mt-5 block">
              <span className="ui-eyebrow">Subject</span>
              <input
                value={emailSubjectDraft}
                onChange={(event) => onEmailSubjectDraftChange(event.target.value)}
                className="mt-2 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400 focus:bg-white"
              />
            </label>
            <label className="mt-4 block">
              <span className="ui-eyebrow">Body</span>
              <textarea
                value={emailBodyDraft}
                onChange={(event) => onEmailBodyDraftChange(event.target.value)}
                rows={12}
                className="mt-2 min-h-56 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm leading-7 text-slate-800 outline-none transition focus:border-slate-400 focus:bg-white"
              />
            </label>
          </>
        ) : null}
      </section>

      <section className="mt-6 rounded-[1.5rem] border bg-white p-5">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Add context</p>
        <textarea
          value={noteDraft}
          onChange={(event) => onNoteDraftChange(event.target.value)}
          placeholder="Capture discovery context, objections, handoff notes, or what changed after the last touch."
          className="mt-3 min-h-28 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400 focus:bg-white"
        />
        <div className="mt-4 flex items-center justify-between gap-4">
          <p className="text-xs text-slate-500">Keep notes light. This is here to preserve context, not create more work.</p>
          <Button disabled={isSavingNote || !noteDraft.trim()} onClick={onSaveNote}>
            {isSavingNote ? "Saving..." : "Save note"}
          </Button>
        </div>
      </section>

      <section className="mt-6">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Relationship history</p>
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
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Client momentum</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">See who is slipping before the relationship cools.</h2>
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
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-300">Warm paths back in</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight">Know who can help reopen a quiet conversation.</h2>
      <p className="mt-3 text-sm leading-6 text-slate-300">
        Brivoly keeps track of referral-backed relationships so a reconnect can come through a warmer path instead of another cold nudge.
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

function MiniFlag({ label, tone }: { label: string; tone: "warning" | "critical" | "neutral" }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] ${
        tone === "critical" ? "bg-rose-100 text-rose-800" : tone === "warning" ? "bg-amber-100 text-amber-800" : "bg-slate-100 text-slate-700"
      }`}
    >
      {label}
    </span>
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

function summarizePriority(item: CRMLeadFollowUp) {
  if (item.recent_email_threads.some((thread) => thread.needs_reply)) {
    return `Reply to ${item.lead_name}`;
  }
  if (item.dormant) {
    return `Reconnect with ${item.lead_name}`;
  }
  if (item.relationship_health_label === "at_risk") {
    return `${item.lead_name} needs a warmer touch`;
  }
  return `${formatStageLabel(item.stage)} for ${item.lead_name}`;
}

function compactPriorityCards<T>(items: (T | null)[]) {
  const seen = new Set<string>();
  const compacted: T[] = [];
  for (const item of items) {
    if (!item || typeof item !== "object" || !("id" in item)) {
      continue;
    }
    const id = String(item.id);
    const leadScopedId = id.split("-").slice(0, 2).join("-");
    if (seen.has(leadScopedId)) {
      continue;
    }
    seen.add(leadScopedId);
    compacted.push(item);
  }
  return compacted;
}

function isProposalFollowThrough(item: CRMLeadFollowUp) {
  const normalized = item.stage.trim().toLowerCase();
  return normalized === "proposal" || normalized === "negotiation";
}

function getNewestThreadTime(item: CRMLeadFollowUp) {
  const timestamps = item.recent_email_threads.map((thread) => new Date(thread.last_message_at).getTime()).filter((value) => !Number.isNaN(value));
  if (!timestamps.length) {
    return null;
  }
  return new Date(Math.max(...timestamps)).toISOString();
}

function getLatestContextEntry(item: CRMLeadFollowUp) {
  const timeline = [...item.timeline];
  timeline.sort((left, right) => new Date(right.occurred_at).getTime() - new Date(left.occurred_at).getTime());
  return timeline[0] ?? null;
}

function getReplySummary(item: CRMLeadFollowUp) {
  const replyThread = item.recent_email_threads.find((thread) => thread.needs_reply);
  if (!replyThread) {
    return item.next_step;
  }
  return replyThread.snippet || item.next_step;
}

function matchesInboxThread(
  item: {
    leadName: string;
    companyName: string;
    notes: string;
    nextStep: string;
    thread: {
      subject: string;
      counterpart_email: string;
      counterpart_name: string;
      snippet: string;
      waiting_on_contact: boolean;
      needs_reply: boolean;
      last_message_at: string;
    };
  },
  query: string,
  filter: InboxFilter,
) {
  const normalizedQuery = query.trim().toLowerCase();
  const queryMatch =
    !normalizedQuery ||
    [
      item.leadName,
      item.companyName,
      item.notes,
      item.nextStep,
      item.thread.subject,
      item.thread.counterpart_email,
      item.thread.counterpart_name,
      item.thread.snippet,
    ]
      .join(" ")
      .toLowerCase()
      .includes(normalizedQuery);

  if (!queryMatch) {
    return false;
  }

  if (filter === "reply") {
    return item.thread.needs_reply;
  }
  if (filter === "waiting") {
    return item.thread.waiting_on_contact;
  }
  if (filter === "quiet") {
    return isQuietThread(item.thread);
  }
  return true;
}

function isQuietThread(thread: {
  last_message_at: string;
  needs_reply: boolean;
  waiting_on_contact: boolean;
}) {
  const ageMs = Date.now() - new Date(thread.last_message_at).getTime();
  return !thread.needs_reply && !thread.waiting_on_contact && ageMs >= 1000 * 60 * 60 * 24 * 7;
}

function describeThreadState(thread: {
  needs_reply: boolean;
  waiting_on_contact: boolean;
  last_message_at: string;
}) {
  if (thread.needs_reply) {
    return "Your reply would keep this moving";
  }
  if (thread.waiting_on_contact) {
    return "You are waiting on them";
  }
  if (isQuietThread(thread)) {
    return "This conversation has gone quiet";
  }
  return `Still warm as of ${formatDateTime(thread.last_message_at)}`;
}

function summarizeThreadPulse(
  thread: {
    snippet: string;
    needs_reply: boolean;
    waiting_on_contact: boolean;
  },
  nextStep: string,
  notes: string,
) {
  const base = thread.snippet.trim() || nextStep.trim() || notes.trim();
  if (thread.needs_reply) {
    return base || "A reply here would keep the relationship moving.";
  }
  if (thread.waiting_on_contact) {
    return base || "This thread is waiting on the other side.";
  }
  return base || "Brivoly is holding onto the last bit of context here.";
}

function formatStageLabel(stage: string) {
  const normalized = stage.trim().toLowerCase();
  if (normalized === "new lead") {
    return "Just getting started";
  }
  if (normalized === "contacted") {
    return "Conversation open";
  }
  if (normalized === "proposal sent") {
    return "Proposal in play";
  }
  if (normalized === "negotiation") {
    return "Working through details";
  }
  if (normalized === "active client") {
    return "Active client";
  }
  if (normalized === "awaiting response") {
    return "Waiting on them";
  }
  return stage;
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

function matchesRelationshipQuery(item: CRMLeadFollowUp, query: string): boolean {
  const normalized = query.trim().toLowerCase();
  if (!normalized) {
    return true;
  }
  const haystack = [
    item.lead_name,
    item.company_name,
    item.owner_name,
    item.notes,
    item.next_step,
    item.stage,
    item.contact_channel,
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(normalized);
}

function matchesRelationshipFilter(item: CRMLeadFollowUp, filter: RelationshipFilter): boolean {
  if (filter === "all") {
    return true;
  }
  if (filter === "due") {
    return isDueNow(item.next_follow_up_at);
  }
  if (filter === "stale") {
    return item.dormant;
  }
  return item.relationship_health_label === "at_risk";
}

function isDueNow(value: string): boolean {
  const dueAt = new Date(value).getTime();
  if (Number.isNaN(dueAt)) {
    return false;
  }
  return dueAt <= Date.now() + 1000 * 60 * 60 * 24;
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
