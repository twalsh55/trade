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
type TodayDraftPreset = {
  objective: CRMEmailDraft["objective"];
  tone: CRMEmailDraft["tone"];
  length: CRMEmailDraft["length"];
  status: string;
};
type TodayPriorityCardItem = {
  id: string;
  href: string;
  eyebrow: string;
  title: string;
  body: string;
  meta: string;
  nextMove?: string;
  actionLabel?: string;
  onAction?: () => void;
};

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
  const [queuedTodayDraft, setQueuedTodayDraft] = useState<{ leadId: string; preset: TodayDraftPreset } | null>(null);
  const [draftFocusToken, setDraftFocusToken] = useState(0);

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
    if (view !== "followups" || !queuedTodayDraft || !selectedLead || selectedLead.id !== queuedTodayDraft.leadId) {
      return;
    }
    generateEmailDraftForLead(selectedLead, queuedTodayDraft.preset);
    setQueuedTodayDraft(null);
  }, [queuedTodayDraft, selectedLead, view]);

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

  function generateEmailDraftForLead(
    lead: CRMLeadFollowUp,
    overrides?: {
      objective?: CRMEmailDraft["objective"];
      tone?: CRMEmailDraft["tone"];
      length?: CRMEmailDraft["length"];
      status?: string;
    },
  ) {
    const objective = overrides?.objective ?? emailObjective;
    const tone = overrides?.tone ?? emailTone;
    const length = overrides?.length ?? emailLength;
    setEmailObjective(objective);
    setEmailTone(tone);
    setEmailLength(length);
    setEmailStatus(overrides?.status ?? "Drafting the next note...");
    startEmailTransition(async () => {
      try {
        const response = await fetch(`/api/crm/followups/email-draft/${lead.id}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            objective,
            tone,
            length,
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

  function generateEmailDraft(overrides?: {
    objective?: CRMEmailDraft["objective"];
    tone?: CRMEmailDraft["tone"];
    length?: CRMEmailDraft["length"];
    status?: string;
  }) {
    const lead = selectedLead;
    if (!lead) {
      return;
    }
    generateEmailDraftForLead(lead, overrides);
  }

  function focusLeadForFollowUp(leadId: string) {
    setRelationshipQuery("");
    setRelationshipFilter("all");
    setSelectedLeadId(leadId);
  }

  function requestDraftFocus() {
    setDraftFocusToken((value) => value + 1);
  }

  function runTodayPriorityAction(leadId: string, route: string, preset?: TodayDraftPreset) {
    focusLeadForFollowUp(leadId);
    if (preset) {
      requestDraftFocus();
      setQueuedTodayDraft({ leadId, preset });
    }
    router.push(route);
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
        description="New accounts should quickly tell Brivoly the business name, sender name for automatic emails, and an optional logo. You can skip it for now, but this is what makes the relationship memory feel like your business instead of a generic tool."
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
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Bring context back in</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">Bring relationship context in without retyping it.</h2>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              Upload a CSV, XLSX, XLS, or note image, or paste a Google Sheets link. Brivoly cleans up messy headers, spots what is missing, and keeps only what is ready to support the next touch.
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
                Spreadsheet or file
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
                Sheet link
              </Button>
            </div>

            {sourceType === "file_upload" ? (
              <section className="mt-5 rounded-[1.4rem] border bg-slate-50/80 p-5">
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">File or note</p>
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
                  Supported: CSV, XLSX, XLS, PNG, JPG, JPEG, and WEBP. Helpful columns include contact, company, owner, next touch, and notes.
                </p>
                {selectedFile ? <p className="mt-2 text-sm font-medium text-slate-700">{selectedFile.name}</p> : null}
                {selectedFile && isImageFile(selectedFile.name) ? (
                  <p className="mt-2 text-xs text-slate-500">
                    Brivoly will use your AI Intake Profile to turn this note image into relationship-ready rows.
                  </p>
                ) : null}
              </section>
            ) : (
              <section className="mt-5 rounded-[1.4rem] border bg-slate-50/80 p-5">
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Sheet link</p>
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
                <p className="mt-3 text-xs text-slate-500">Use a shareable Google Sheets URL. Brivoly will pull the context in directly.</p>
              </section>
            )}

            <div className="mt-5 flex flex-wrap gap-3">
              <Button disabled={isImportPending} onClick={() => requestImportPreview()}>
                  {isImportPending ? "Checking..." : importPreview ? "Re-check context" : "Check context"}
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
                {isImportPending ? "Importing..." : "Bring this in"}
              </Button>
            </div>

            {importError ? <p className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{importError}</p> : null}
            {importStatus ? <p className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{importStatus}</p> : null}
            {isImportMappingDirty ? (
              <p className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                Column mappings changed. Re-check the preview so Brivoly can validate the updated layout before bringing this in.
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
            onRunAction={runTodayPriorityAction}
          />
        </div>
      ) : null}

      {showingFollowups ? (
      <section className="mt-6 grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <section className="rounded-[1.75rem] border bg-white/80 p-6 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Relationship memory</p>
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
                        {item.relationship_state === "stale" ? <MiniFlag tone="warning" label="Stale" /> : null}
                        {item.relationship_state === "drifting" ? <MiniFlag tone="warning" label="Drifting" /> : null}
                        {item.relationship_state === "at_risk" ? <MiniFlag tone="critical" label="At risk" /> : null}
                        <PriorityBadge priority={item.priority} />
                      </div>
                    </div>
                    <p className="mt-4 text-sm font-medium text-slate-700">Next touch</p>
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
              draftFocusToken={draftFocusToken}
              onEmailObjectiveChange={setEmailObjective}
              onEmailToneChange={setEmailTone}
              onEmailLengthChange={setEmailLength}
              onEmailSubjectDraftChange={setEmailSubjectDraft}
              onEmailBodyDraftChange={setEmailBodyDraft}
              onGenerateEmailDraft={generateEmailDraft}
            />
          ) : null}
          <section className="rounded-[1.75rem] border bg-slate-950 p-6 text-slate-50 shadow-[0_24px_90px_-55px_rgba(15,23,42,0.9)]">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-300">Why Brivoly feels lighter</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight">Brivoly remembers relationships so freelancers do not have to.</h2>
            <ul className="mt-5 space-y-3 text-sm leading-6 text-slate-300">
              <li>Every note, reminder, and suggested message should lower mental overhead instead of adding admin.</li>
              <li>Brivoly should help you stay warm, responsive, and top-of-mind without more software work.</li>
              <li>The goal is continuity and follow-through, not stage management.</li>
            </ul>
          </section>
        </section>
      </section>
      ) : null}

      {showingInbox ? (
        <section className="mt-6 grid gap-6 xl:grid-cols-[0.92fr_1.08fr]">
          <section className="rounded-[1.75rem] border bg-white/85 p-6 shadow-sm">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Inbox memory</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">Let Brivoly keep relationship context current from email.</h2>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              Brivoly turns email activity into living relationship memory: it matches contacts by email, creates missing contacts automatically, and keeps the right conversation attached to the right person.
            </p>

            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <CompactMetricLight label="Reply soon" value={String(overview.inbox_summary?.needs_reply_count ?? 0)} tone="critical" />
              <CompactMetricLight label="Waiting on them" value={String(overview.inbox_summary?.waiting_on_contact_count ?? 0)} tone="warning" />
              <CompactMetricLight label="Quiet threads" value={String(overview.inbox_summary?.stale_thread_count ?? 0)} tone="neutral" />
            </div>

            <section className="mt-6 rounded-[1.4rem] border bg-slate-50/80 p-5">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Inbox sync preview</p>
            <p className="mt-2 text-sm leading-6 text-slate-600">
                Use this to test inbox memory before Gmail or Outlook connections are live.
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
                onDraftAction={(draft) => generateEmailDraft(draft)}
                isDrafting={isEmailPending}
                draftStatus={emailStatus}
              />
            ) : null}
          </section>

          <InboxActivityPanel
            items={overview.items}
            selectedLeadId={selectedLead?.id ?? null}
            onSelectLead={setSelectedLeadId}
            onDraftAction={(leadId, draft) => {
              focusLeadForFollowUp(leadId);
              requestDraftFocus();
              setQueuedTodayDraft({ leadId, preset: draft });
              void router.push("/clientos/follow-ups");
            }}
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
            inboxSummary={overview.inbox_summary}
            onRunAction={runTodayPriorityAction}
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
      eyebrow: "Relationship memory",
      title: "Never lose track of where a relationship stands.",
      body: "Keep notes, context, and the next touch together so client continuity does not depend on your memory alone.",
    },
    inbox: {
      eyebrow: "Inbox memory",
      title: "Let email quietly keep relationship memory up to date.",
      body: "Brivoly turns inbox activity into context, summaries, and follow-through without asking you to log everything by hand.",
    },
    pipeline: {
      eyebrow: "Attention",
      title: "See who is slipping before the relationship cools.",
      body: "Use this page to spot quiet relationships, reopening moments, and where a gentle reconnect is due.",
    },
    import: {
      eyebrow: "Bring context back in",
      title: "Bring older client context back into memory without extra cleanup.",
      body: "Upload spreadsheets and raw note images, let Brivoly make sense of them, and only keep what supports better follow-through.",
    },
    intake: {
      eyebrow: "Client dropzone",
      title: "Make it easy for clients to send context when it matters.",
      body: "Use no-login upload links, simple default paths, and mobile-first capture so updates land in relationship memory without extra back-and-forth.",
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
  inboxSummary,
  onRunAction,
}: {
  items: CRMLeadFollowUp[];
  inboxSummary: CRMFollowUpOverview["inbox_summary"];
  onRunAction: (leadId: string, route: string, preset?: TodayDraftPreset) => void;
}) {
  const replyLead = [...items]
    .filter((item) => item.recent_email_threads.some((thread) => thread.needs_reply))
    .sort((left, right) => compareReplyPriority(left, right))[0] ?? null;
  const reconnectLead = [...items]
    .filter((item) => item.relationship_state === "stale" || item.relationship_state === "at_risk" || item.relationship_state === "drifting")
    .sort((left, right) => compareReconnectPriority(left, right))[0] ?? null;
  const proposalLead = [...items]
    .filter((item) => isProposalFollowThrough(item))
    .sort((left, right) => compareProposalPriority(left, right))[0] ?? null;
  const recentUploadLead = [...items]
    .filter((item) => hasRecentUploadContext(item))
    .sort((left, right) => compareRecentUploadPriority(left, right))[0] ?? null;
  const recentContextLead = [...items]
    .filter((item) => hasFreshContext(item) && !hasRecentUploadContext(item))
    .sort((left, right) => compareFreshContextPriority(left, right))[0] ?? null;
  const replyThread = replyLead ? getReplyThread(replyLead) : null;

  const uploadReentryLead = recentUploadLead && isReconnectMoment(recentUploadLead) ? recentUploadLead : null;

  const priorities = compactPriorityCards<TodayPriorityCardItem>([
    uploadReentryLead
      ? {
          id: `${uploadReentryLead.id}-upload-reconnect`,
          href: "/clientos/follow-ups",
          eyebrow: "Fresh way back in",
          title: `Use new context to reopen ${uploadReentryLead.lead_name}`,
          body: uploadReentryLead.relationship_reconnect_why_now || uploadReentryLead.relationship_upload_follow_through_hint || uploadReentryLead.relationship_recent_upload_summary,
          meta: `${uploadReentryLead.company_name} · ${formatDateTime(getLatestUploadContextEntry(uploadReentryLead)?.occurred_at ?? null)}`,
          nextMove: uploadReentryLead.relationship_reconnect_next_move || uploadReentryLead.relationship_upload_follow_through_hint || "Use the fresh context to restart the thread gently.",
          actionLabel: "Draft reconnect",
          onAction: () =>
            onRunAction(uploadReentryLead.id, "/clientos/follow-ups", {
              objective: "revive",
              tone: "warm",
              length: "short",
              status: "Drafting a reconnect from fresh client context...",
            }),
        }
      : null,
    replyLead
      ? {
          id: `${replyLead.id}-reply`,
          href: "/clientos/inbox",
          eyebrow: "Reply soon",
          title: `Reply to ${replyLead.lead_name}`,
          body: replyThread?.next_touch_hint || replyThread?.memory_summary || getReplySummary(replyLead),
          meta: `${replyLead.company_name} · ${formatDateTime(getNewestThreadTime(replyLead) ?? replyLead.next_follow_up_at)}`,
          nextMove: replyThread?.open_loop || replyThread?.carry_forward_hint || "Pick up the thread while the context is still fresh.",
          actionLabel: "Draft reply",
          onAction: () =>
            onRunAction(replyLead.id, "/clientos/follow-ups", {
              objective: "follow_up",
              tone: "warm",
              length: "short",
              status: "Drafting a reply from Today...",
            }),
        }
      : null,
    reconnectLead && reconnectLead.id !== uploadReentryLead?.id
      ? {
          id: `${reconnectLead.id}-reconnect`,
          href: "/clientos/follow-ups",
          eyebrow: "Reconnect",
          title: `Reconnect with ${reconnectLead.lead_name}`,
          body: reconnectLead.relationship_reconnect_why_now || reconnectLead.relationship_timing_nudge || reconnectLead.relationship_reminders[0]?.message || reconnectLead.next_step,
          meta: `${reconnectLead.company_name} · last meaningful touch ${formatDateTime(reconnectLead.last_meaningful_interaction_at)}`,
          nextMove: reconnectLead.relationship_reconnect_next_move || reconnectLead.relationship_reconnect_message_hint || "Use a short, low-pressure check-in.",
          actionLabel: "Draft reconnect",
          onAction: () =>
            onRunAction(reconnectLead.id, "/clientos/follow-ups", {
              objective: "revive",
              tone: "warm",
              length: "short",
              status: "Drafting a reconnect from Today...",
            }),
        }
      : null,
    proposalLead
      ? {
          id: `${proposalLead.id}-proposal`,
          href: "/clientos/follow-ups",
          eyebrow: "Proposal follow-up",
          title: `Keep momentum with ${proposalLead.lead_name}`,
          body: proposalLead.relationship_timing_nudge || proposalLead.next_step,
          meta: `${proposalLead.company_name} · follow up by ${formatDateTime(proposalLead.next_follow_up_at)}`,
          nextMove: proposalLead.next_step || "Send the lightest possible nudge that moves the thread forward.",
          actionLabel: "Draft nudge",
          onAction: () =>
            onRunAction(proposalLead.id, "/clientos/follow-ups", {
              objective: "follow_up",
              tone: "confident",
              length: "short",
              status: "Drafting a proposal nudge from Today...",
            }),
        }
      : null,
    recentUploadLead && recentUploadLead.id !== uploadReentryLead?.id
      ? {
          id: `${recentUploadLead.id}-upload`,
          href: "/clientos/follow-ups",
          eyebrow: isReconnectMoment(recentUploadLead) ? "Fresh way back in" : "Client upload",
          title: isReconnectMoment(recentUploadLead) ? `Use new context to reopen ${recentUploadLead.lead_name}` : `Review new files from ${recentUploadLead.lead_name}`,
          body:
            (isReconnectMoment(recentUploadLead)
              ? recentUploadLead.relationship_reconnect_why_now || recentUploadLead.relationship_upload_follow_through_hint
              : undefined) ||
            recentUploadLead.relationship_upload_follow_through_hint ||
            `${recentUploadLead.relationship_recent_upload_summary}${recentUploadLead.next_step.trim() ? ` Next touch: ${recentUploadLead.next_step}` : ""}`,
          meta: `${recentUploadLead.company_name} · ${formatDateTime(getLatestUploadContextEntry(recentUploadLead)?.occurred_at ?? null)}`,
          nextMove: recentUploadLead.relationship_upload_follow_through_hint || recentUploadLead.relationship_reconnect_next_move || "Turn the fresh client context into a quick follow-through note.",
          actionLabel: isReconnectMoment(recentUploadLead) ? "Draft reconnect" : "Draft note",
          onAction: () =>
            onRunAction(recentUploadLead.id, "/clientos/follow-ups", {
              objective: isReconnectMoment(recentUploadLead) ? "revive" : "recap",
              tone: "warm",
              length: "short",
              status: isReconnectMoment(recentUploadLead) ? "Drafting a reconnect from fresh client context..." : "Drafting a note from fresh client context...",
            }),
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
          nextMove: recentContextLead.next_step || "Open the relationship and decide whether this changes the next touch.",
          actionLabel: "Open relationship",
          onAction: () => onRunAction(recentContextLead.id, "/clientos/follow-ups"),
        }
      : null,
  ]);

  const fallbackPriorities: TodayPriorityCardItem[] = items.slice(0, 4).map((item) => ({
    id: item.id,
    href: "/clientos/follow-ups",
    eyebrow: "Next touch",
    title: summarizePriority(item),
    body: item.next_step,
    meta: `${item.lead_name} · ${formatDateTime(item.next_follow_up_at)}`,
    nextMove: item.relationship_timing_nudge || "Open the relationship and take the smallest useful next step.",
  }));
  const visiblePriorities = (priorities.length ? priorities : fallbackPriorities).slice(0, 4);
  const primaryPriority = visiblePriorities[0] ?? null;
  const secondaryPriorities = visiblePriorities.slice(1);

  const replyCount = inboxSummary?.needs_reply_count ?? 0;
  const reconnectCount = items.filter((item) => item.relationship_state === "stale" || item.relationship_state === "at_risk" || item.relationship_state === "drifting").length;
  const proposalCount = items.filter((item) => isProposalFollowThrough(item)).length;
  const recentUploadCount = items.filter((item) => hasRecentUploadContext(item)).length;
  const freshContextCount = items.filter((item) => hasFreshContext(item)).length;
  const urgentCount = replyCount + proposalCount + reconnectCount;
  const contextCount = recentUploadCount + Math.max(0, freshContextCount - recentUploadCount);

  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Today’s priorities</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">A short list of who needs your attention right now.</h2>
      <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
        Brivoly pulls together replies, reconnects, proposal follow-through, and new client context so you can pick the right next move without re-reading everything first.
      </p>
      <p className="mt-3 text-sm font-medium text-slate-700">Start with one relationship and one next move. Brivoly will hold the rest.</p>
      <div className="mt-4 flex flex-wrap gap-2">
        {visiblePriorities.slice(0, 2).map((item) => (
          <button
            key={`${item.id}-quick-start`}
            type="button"
            onClick={() => {
              if (item.onAction) {
                item.onAction();
                return;
              }
              window.location.assign(item.href);
            }}
            className="rounded-full border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-700 transition hover:border-slate-400 hover:bg-white hover:text-slate-950"
          >
            {item.actionLabel ?? item.eyebrow}
          </button>
        ))}
      </div>
      <div className="mt-5 grid gap-3 md:grid-cols-2">
        <TodaySignal
          label="Needs care now"
          value={urgentCount ? String(urgentCount) : "Clear"}
          detail={
            urgentCount
              ? `${replyCount ? `${replyCount} repl${replyCount === 1 ? "y" : "ies"}` : "no replies"}, ${reconnectCount ? `${reconnectCount} reconnect${reconnectCount === 1 ? "" : "s"}` : "no reconnects"}, and ${proposalCount ? `${proposalCount} proposal follow-up${proposalCount === 1 ? "" : "s"}` : "no proposal nudges"}`
              : "Nothing urgent is stacking up right now"
          }
        />
        <TodaySignal
          label="Freshest opening"
          value={contextCount ? String(contextCount) : "Quiet"}
          detail={
            recentUploadCount
              ? `${recentUploadCount} client upload${recentUploadCount === 1 ? "" : "s"} landed recently`
              : freshContextCount
                ? `${freshContextCount} relationship${freshContextCount === 1 ? "" : "s"} picked up new context recently`
                : "No new client context landed overnight"
          }
        />
      </div>
      {primaryPriority ? (
        <div className="mt-5 rounded-[1.5rem] border border-slate-900 bg-slate-950 px-5 py-5 text-white shadow-sm">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-2xl">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-200">Start here</p>
              <p className="mt-2 text-2xl font-semibold tracking-tight">{primaryPriority.title}</p>
              <p className="mt-3 text-sm leading-6 text-slate-200">{primaryPriority.body}</p>
              {primaryPriority.nextMove ? (
                <div className="mt-4 rounded-[1rem] border border-white/10 bg-white/5 px-4 py-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-200">Next move</p>
                  <p className="mt-2 text-sm leading-6 text-slate-100">{primaryPriority.nextMove}</p>
                </div>
              ) : null}
              <p className="mt-3 text-sm leading-6 text-slate-300">Take the smallest next step here first, then let Brivoly hold the rest of the context in place.</p>
              <p className="mt-4 text-xs text-slate-300">{primaryPriority.meta}</p>
              <p className="mt-3 text-xs uppercase tracking-[0.16em] text-slate-400">{primaryPriority.eyebrow}</p>
            </div>
            <div className="flex flex-wrap gap-2 lg:justify-end">
              <Button
                type="button"
                onClick={primaryPriority.onAction}
                className="border border-white/20 bg-white text-slate-950 hover:bg-slate-100"
              >
                {primaryPriority.actionLabel ?? "Open"}
              </Button>
              <Button asChild variant="outline" className="border-white/20 bg-transparent text-white hover:bg-white/10 hover:text-white">
                <Link href={primaryPriority.href}>Open relationship</Link>
              </Button>
            </div>
          </div>
        </div>
      ) : null}
      {secondaryPriorities.length ? (
        <div className="mt-5 grid gap-3 md:grid-cols-2">
          {secondaryPriorities.map((item) => (
            <PriorityCard
              key={item.id}
              href={item.href}
              eyebrow={item.eyebrow}
              title={item.title}
              body={item.body}
              meta={item.meta}
              nextMove={item.nextMove}
              actionLabel={item.actionLabel}
              onAction={item.onAction}
            />
          ))}
        </div>
      ) : null}
      <div className="mt-5 flex flex-wrap gap-3">
        <QuickLinkPill href="/clientos/follow-ups" title="Relationship memory" body="Keep the last touch, the next touch, and the full story together." />
        <QuickLinkPill href="/clientos/inbox" title="Inbox continuity" body="Let email carry the thread forward without extra logging." />
      </div>
    </section>
  );
}

function TodaySignal({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="min-w-0 overflow-hidden rounded-[1.2rem] border bg-slate-50/80 px-5 py-5">
      <div className="flex items-start justify-between gap-4">
        <p className="max-w-[16rem] break-words text-xs font-semibold uppercase tracking-[0.14em] text-slate-400 [overflow-wrap:anywhere] sm:tracking-[0.18em]">
          {label}
        </p>
        <p className="shrink-0 text-3xl font-semibold tracking-tight text-slate-950">{value}</p>
      </div>
      <p className="mt-4 max-w-[24rem] break-words text-sm leading-6 text-slate-700 [overflow-wrap:anywhere]">{detail}</p>
    </div>
  );
}

function QuickLinkPill({ href, title, body }: { href: string; title: string; body: string }) {
  return (
    <Link
      href={href}
      className="inline-flex min-w-0 max-w-full items-center gap-2 rounded-full border bg-slate-50/80 px-4 py-3 text-sm text-slate-700 transition hover:border-slate-400 hover:bg-white hover:text-slate-950"
    >
      <span className="font-semibold text-slate-950">{title}</span>
      <span className="text-slate-400">·</span>
      <span className="truncate">{body}</span>
    </Link>
  );
}

function RelationshipContinuityPanel({ summary }: { summary: NonNullable<CRMFollowUpOverview["relationship_summary"]> }) {
  const steadyCount = summary.active_count + summary.warm_count;
  const needsCareCount = summary.drifting_count + summary.stale_count + summary.at_risk_count;
  const warmMoments = summary.referral_reminder_count + summary.milestone_reminder_count;
  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Relationship continuity</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">Stay warm without holding everything in your head.</h2>
      <div className="mt-5 rounded-[1.3rem] border bg-slate-50/80 px-5 py-5">
        <p className="text-sm leading-7 text-slate-700">
          <span className="font-semibold text-slate-950">{steadyCount}</span> relationship{steadyCount === 1 ? "" : "s"} still feel steady.
          {" "}
          {needsCareCount
            ? <><span className="font-semibold text-slate-950">{needsCareCount}</span> may need a warmer touch soon.</>
            : "Nothing feels especially fragile right now."}
          {" "}
          {summary.warm_intro_connections.length
            ? `${summary.warm_intro_connections.length} warm re-entry path${summary.warm_intro_connections.length === 1 ? "" : "s"} could help reopen a thread more naturally.`
            : ""}
          {" "}
          {warmMoments
            ? `${warmMoments} thoughtful moment${warmMoments === 1 ? "" : "s"} could make the next touch easier.`
            : ""}
        </p>
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
  nextMove,
  actionLabel,
  onAction,
}: {
  href: string;
  eyebrow: string;
  title: string;
  body: string;
  meta: string;
  nextMove?: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className="min-w-0 overflow-hidden rounded-[1.35rem] border bg-slate-50/80 px-5 py-5 transition hover:border-slate-400 hover:bg-white">
      <Link href={href} className="block min-w-0">
        <p className="break-words text-xs font-semibold uppercase tracking-[0.14em] text-slate-400 [overflow-wrap:anywhere] sm:tracking-[0.18em]">{eyebrow}</p>
        <p className="break-words text-lg font-semibold tracking-tight text-slate-950 [overflow-wrap:anywhere]">{title}</p>
        <p className="mt-2 break-words text-sm leading-6 text-slate-600 [overflow-wrap:anywhere]">{body}</p>
        {nextMove ? <p className="mt-3 break-words text-sm leading-6 text-slate-800 [overflow-wrap:anywhere]"><span className="font-medium text-slate-950">Next move:</span> {nextMove}</p> : null}
        <p className="mt-3 break-words text-xs text-slate-500 [overflow-wrap:anywhere]">{meta}</p>
      </Link>
      {actionLabel && onAction ? (
        <div className="mt-4 flex justify-start">
          <button
            type="button"
            onClick={onAction}
            className="rounded-full border border-slate-300 bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-slate-700 transition hover:border-slate-500 hover:text-slate-950"
          >
            {actionLabel}
          </button>
        </div>
      ) : null}
    </div>
  );
}

function PipelineBoardPanel({
  summary,
  items,
  selectedLeadId,
  onSelectLead,
  onRunAction,
}: {
  summary: CRMPipelineStageSummary[];
  items: CRMLeadFollowUp[];
  selectedLeadId: string | null;
  onSelectLead: (leadId: string) => void;
  onRunAction: (leadId: string, route: string, preset?: TodayDraftPreset) => void;
}) {
  const itemsByStage = new Map<string, CRMLeadFollowUp[]>();
  for (const item of items) {
    const bucket = itemsByStage.get(item.stage) ?? [];
    bucket.push(item);
    itemsByStage.set(item.stage, bucket);
  }
  const needsCareFirst = [...items]
    .filter((item) => relationshipStateUrgency(item.relationship_state) > 0 || item.recent_email_threads.some((thread) => thread.needs_reply))
    .sort((left, right) => compareAttentionPriority(left, right))
    .slice(0, 4);

  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm xl:col-span-2">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-2xl">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Relationship attention</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">Protect the relationships that are easiest to lose.</h2>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            This page is for quiet threads, overdue replies, and gentle re-entry moments. The goal is continuity and warmth, not system-heavy tracking.
          </p>
        </div>
        <div className="rounded-[1.2rem] border bg-slate-50/80 px-4 py-4 lg:max-w-sm">
          <p className="text-sm leading-6 text-slate-700">
            <span className="font-semibold text-slate-950">{summary.reduce((total, stage) => total + stage.overdue_count, 0)}</span> relationship{summary.reduce((total, stage) => total + stage.overdue_count, 0) === 1 ? "" : "s"} need a touch,
            {" "}
            <span className="font-semibold text-slate-950">{summary.reduce((total, stage) => total + stage.dormant_count, 0)}</span> feel quiet,
            {" "}
            and <span className="font-semibold text-slate-950">{summary.reduce((total, stage) => total + stage.high_priority_count, 0)}</span> still have warm openings.
          </p>
        </div>
      </div>

      {needsCareFirst.length ? (
        <div className="mt-6 rounded-[1.5rem] border bg-slate-50/80 p-4">
          <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Gentle re-entry first</p>
              <p className="mt-2 text-sm leading-6 text-slate-600">Start here if you want the shortest path to keeping a relationship warm before it fully slips.</p>
            </div>
            <p className="text-xs text-slate-500">Reply pressure and quiet relationships surface before stage lanes do.</p>
          </div>
          <div className="mt-4 grid gap-3 xl:grid-cols-2">
            {needsCareFirst.map((item) => {
              const selected = item.id === selectedLeadId;
              const reconnectable = isReconnectMoment(item);
              return (
                <div
                  key={`${item.id}-needs-care`}
                  className={`rounded-[1.2rem] border px-4 py-4 text-left transition ${
                    selected ? "border-slate-900 bg-white shadow-sm" : "border-slate-200 bg-white/90 hover:border-slate-400"
                  }`}
                >
                  <button type="button" onClick={() => onSelectLead(item.id)} className="block w-full text-left">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-slate-950">{item.lead_name}</p>
                        <p className="mt-1 text-xs text-slate-500">{item.company_name}</p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {item.relationship_state === "stale" ? <MiniFlag tone="warning" label="Stale" /> : null}
                        {item.relationship_state === "drifting" ? <MiniFlag tone="warning" label="Drifting" /> : null}
                        {item.relationship_state === "at_risk" ? <MiniFlag tone="critical" label="At risk" /> : null}
                        {item.recent_email_threads.some((thread) => thread.needs_reply) ? <MiniFlag tone="critical" label="Reply" /> : null}
                      </div>
                    </div>
                    <p className="mt-3 text-sm leading-6 text-slate-700">{item.relationship_reconnect_why_now || item.relationship_timing_nudge || item.next_step}</p>
                    {reconnectable ? (
                      <div className="mt-3 rounded-xl border bg-slate-50 px-3 py-3">
                        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">Best re-entry</p>
                        <p className="mt-2 text-sm leading-6 text-slate-700">{item.relationship_reconnect_next_move || item.next_step}</p>
                        <p className="mt-3 text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">Why it can still land</p>
                        <p className="mt-2 text-sm leading-6 text-slate-700">{describeReconnectWindow(item)}</p>
                        <p className="mt-3 text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">Starter line</p>
                        <p className="mt-2 text-sm leading-6 text-slate-700">{buildReconnectStarterLine(item)}</p>
                      </div>
                    ) : null}
                    <p className="mt-3 text-xs text-slate-500">
                      {formatDateTime(item.last_meaningful_interaction_at)} · {formatStageLabel(item.stage)}
                    </p>
                  </button>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => onSelectLead(item.id)}
                      className="rounded-full border border-slate-300 bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-slate-700 transition hover:border-slate-500 hover:text-slate-950"
                    >
                      Open relationship
                    </button>
                    {reconnectable ? (
                      <button
                        type="button"
                        onClick={() =>
                          onRunAction(item.id, "/clientos/follow-ups", {
                            objective: "revive",
                            tone: "warm",
                            length: "short",
                            status: "Drafting a reconnect from Attention...",
                          })
                        }
                        className="rounded-full border border-slate-300 bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-slate-700 transition hover:border-slate-500 hover:text-slate-950"
                      >
                        Draft reconnect
                      </button>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

      <div className="mt-6 flex gap-4 overflow-x-auto pb-2">
        {summary.map((stage) => {
          const stageItems = [...(itemsByStage.get(stage.stage) ?? [])].sort((left, right) => compareAttentionPriority(left, right));
          return (
            <section
              key={stage.stage}
              className="min-w-[280px] flex-1 rounded-[1.5rem] border bg-slate-50/80 p-4"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Relationship lane</p>
                  <h3 className="mt-2 text-xl font-semibold tracking-tight text-slate-950">{stage.stage}</h3>
                </div>
                <div className="rounded-full border border-slate-200 bg-white px-3 py-1 text-sm font-semibold text-slate-700">
                  {stage.lead_count}
                </div>
              </div>

              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                <TimelineTile label="Needs a touch" value={String(stage.overdue_count)} />
                <TimelineTile label="Due soon" value={String(stage.due_this_week_count)} />
                <TimelineTile label="Openings" value={String(stage.high_priority_count)} />
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
                        <div className="flex flex-wrap gap-2">
                          {item.relationship_state === "stale" ? <MiniFlag tone="warning" label="Stale" /> : null}
                          {item.relationship_state === "drifting" ? <MiniFlag tone="warning" label="Drifting" /> : null}
                          {item.relationship_state === "at_risk" ? <MiniFlag tone="critical" label="At risk" /> : null}
                          <PriorityBadge priority={item.priority} />
                        </div>
                      </div>
                      <p className="mt-3 text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">Needs attention by</p>
                      <p className="mt-1 text-sm text-slate-700">{formatDateTime(item.next_follow_up_at)}</p>
                      <p className="mt-3 text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">Best next touch</p>
                      <p className="mt-1 text-sm leading-6 text-slate-600">{isReconnectMoment(item) ? item.relationship_reconnect_next_move || item.next_step : item.next_step}</p>
                      {isReconnectMoment(item) ? (
                        <p className="mt-3 text-sm leading-6 text-slate-600">{buildReconnectStarterLine(item)}</p>
                      ) : null}
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
  onDraftAction,
  inboxQuery,
  inboxFilter,
  onInboxQueryChange,
  onInboxFilterChange,
}: {
  items: CRMLeadFollowUp[];
  selectedLeadId: string | null;
  onSelectLead: (leadId: string) => void;
  onDraftAction: (
    leadId: string,
    draft: {
      objective: CRMEmailDraft["objective"];
      tone: CRMEmailDraft["tone"];
      length: CRMEmailDraft["length"];
      status: string;
    },
  ) => void;
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
        thread,
      })),
    )
    .sort((left, right) => new Date(right.thread.last_message_at).getTime() - new Date(left.thread.last_message_at).getTime());
  const filteredThreads = threads.filter((item) => matchesInboxThread(item, inboxQuery, inboxFilter));
  const urgentThreads = filteredThreads.filter(({ thread }) => thread.needs_reply || thread.waiting_on_contact || isQuietThread(thread));
  const steadyThreads = filteredThreads.filter(({ thread }) => !(thread.needs_reply || thread.waiting_on_contact || isQuietThread(thread)));

  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Relationship activity</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">Recent conversations Brivoly is quietly holding together.</h2>
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
      </div>
      <div className="mt-6 space-y-6">
        {urgentThreads.length ? (
          <div>
            <div className="flex items-end justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Needs you now</p>
                <p className="mt-2 text-sm leading-6 text-slate-600">These threads are waiting on you, starting to drift, or worth reopening before the relationship loses warmth.</p>
              </div>
              <p className="text-xs text-slate-500">{urgentThreads.length} conversation{urgentThreads.length === 1 ? "" : "s"}</p>
            </div>
            <div className="mt-4 space-y-4">
              {urgentThreads.map((item) => (
                <InboxThreadCard key={item.thread.thread_id} item={item} selected={item.leadId === selectedLeadId} onSelectLead={onSelectLead} onDraftAction={onDraftAction} />
              ))}
            </div>
          </div>
        ) : null}
        {steadyThreads.length ? (
          <div>
            <div className="flex items-end justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Still warm</p>
                <p className="mt-2 text-sm leading-6 text-slate-600">Brivoly is holding onto the context here so you can step back in without rereading the whole thread.</p>
              </div>
              <p className="text-xs text-slate-500">{steadyThreads.length} conversation{steadyThreads.length === 1 ? "" : "s"}</p>
            </div>
            <div className="mt-4 space-y-4">
              {steadyThreads.map((item) => (
                <InboxThreadCard key={item.thread.thread_id} item={item} selected={item.leadId === selectedLeadId} onSelectLead={onSelectLead} onDraftAction={onDraftAction} />
              ))}
            </div>
          </div>
        ) : null}
        {!filteredThreads.length ? (
          <div className="rounded-[1.35rem] border border-dashed bg-slate-50/70 p-6 text-sm leading-6 text-slate-600">
            No conversations match this view yet. Once inbox sync is flowing, this becomes the quiet memory layer for who said what and who needs a reply.
          </div>
        ) : null}
      </div>
    </section>
  );
}

function InboxThreadCard({
  item,
  selected,
  onSelectLead,
  onDraftAction,
}: {
  item: {
    leadId: string;
    leadName: string;
    companyName: string;
    stage: string;
    thread: CRMLeadFollowUp["recent_email_threads"][number];
  };
  selected: boolean;
  onSelectLead: (leadId: string) => void;
  onDraftAction: (
    leadId: string,
    draft: {
      objective: CRMEmailDraft["objective"];
      tone: CRMEmailDraft["tone"];
      length: CRMEmailDraft["length"];
      status: string;
    },
  ) => void;
}) {
  const { leadId, leadName, companyName, stage, thread } = item;

  return (
    <div
      className={`block w-full rounded-[1.35rem] border px-5 py-5 text-left transition ${
        selected ? "border-slate-900 bg-white shadow-sm" : "bg-slate-50/80 hover:border-slate-400 hover:bg-white"
      }`}
    >
      <button type="button" onClick={() => onSelectLead(leadId)} className="block w-full text-left">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
              {formatStageLabel(stage)} · {thread.last_message_direction === "inbound" ? "Needs your reply" : "Waiting on them"}
            </p>
            <h3 className="mt-2 text-xl font-semibold tracking-tight text-slate-950">{thread.subject}</h3>
            <p className="mt-1 text-sm text-slate-600">
              {leadName} · {companyName}
            </p>
            <p className="mt-3 text-sm font-medium text-slate-900">{thread.relationship_pulse}</p>
            {thread.continuity_memory ? <p className="mt-2 text-sm leading-6 text-slate-700">{thread.continuity_memory}</p> : null}
            <p className="mt-2 text-sm leading-6 text-slate-600">{thread.continuity_span}</p>
            <p className="mt-3 text-sm leading-6 text-slate-600">{thread.memory_summary}</p>
            {thread.carry_forward_hint ? <p className="mt-3 text-sm leading-6 text-slate-700">{thread.carry_forward_hint}</p> : null}
            {thread.unresolved_hint ? <p className="mt-3 text-sm leading-6 text-slate-700">{thread.unresolved_hint}</p> : null}
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
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <TimelineTile label="Brivoly read" value={thread.next_touch_hint} />
          <TimelineTile label="Open loop" value={thread.open_loop} />
          <TimelineTile label="What changed" value={thread.recent_change_hint} />
          <TimelineTile label="Last turn" value={formatDateTime(thread.last_message_at)} />
        </div>
      </button>
      <div className="mt-4 flex flex-wrap gap-3">
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            onDraftAction(
              leadId,
              thread.needs_reply
                ? {
                    objective: "follow_up",
                    tone: "warm",
                    length: "short",
                    status: "Drafting a reply from Inbox...",
                  }
                : {
                    objective: "revive",
                    tone: "warm",
                    length: "short",
                    status: "Drafting a reconnect from Inbox...",
                  },
            );
          }}
        >
          {thread.needs_reply ? "Draft reply" : "Draft reconnect"}
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            onSelectLead(leadId);
          }}
        >
          Open relationship
        </Button>
      </div>
    </div>
  );
}

function InboxNextMovePanel({
  lead,
  onDraftAction,
  isDrafting,
  draftStatus,
}: {
  lead: CRMLeadFollowUp;
  onDraftAction: (draft: {
    objective: CRMEmailDraft["objective"];
    tone: CRMEmailDraft["tone"];
    length: CRMEmailDraft["length"];
    status: string;
  }) => void;
  isDrafting: boolean;
  draftStatus: string | null;
}) {
  const latestThread = [...lead.recent_email_threads].sort(
    (left, right) => new Date(right.last_message_at).getTime() - new Date(left.last_message_at).getTime(),
  )[0] ?? null;
  const quietReconnect = latestThread ? isQuietThread(latestThread) && !latestThread.needs_reply : false;
  const shouldReconnect = quietReconnect || isReconnectMoment(lead);
  const primaryAction = shouldReconnect
    ? {
        label: "Draft reconnect",
        draft: {
          objective: "revive" as const,
          tone: "warm" as const,
          length: "short" as const,
          status: "Drafting a gentle reconnect from Inbox...",
        },
      }
    : {
        label: "Draft reply",
        draft: {
          objective: "follow_up" as const,
          tone: "warm" as const,
          length: "short" as const,
          status: "Drafting a reply that keeps the thread moving...",
        },
      };

  return (
    <section className="mt-6 rounded-[1.4rem] border bg-white p-5 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Next move</p>
      <h3 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">{lead.lead_name}</h3>
      <p className="mt-1 text-sm text-slate-600">{lead.company_name}</p>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <TimelineTile label="Brivoly read" value={latestThread ? latestThread.next_touch_hint : "No synced thread yet"} />
        <TimelineTile
          label="Recommended next touch"
          value={
            lead.relationship_upload_follow_through_hint ||
            (shouldReconnect ? lead.relationship_reconnect_next_move || lead.next_step : lead.next_step)
          }
        />
      </div>
      {latestThread ? (
        <div className="mt-4 rounded-[1.2rem] border bg-slate-50/80 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Latest thread</p>
          <p className="mt-2 text-sm font-medium text-slate-900">{latestThread.subject}</p>
          <p className="mt-2 text-sm font-medium text-slate-900">{latestThread.relationship_pulse}</p>
          {latestThread.continuity_memory ? <p className="mt-2 text-sm leading-6 text-slate-700">{latestThread.continuity_memory}</p> : null}
          <p className="mt-2 text-sm leading-6 text-slate-600">{latestThread.continuity_span}</p>
          <p className="mt-2 text-sm leading-6 text-slate-600">{latestThread.memory_summary}</p>
        </div>
      ) : null}
      {latestThread?.continuity_memory || latestThread?.recent_change_hint || latestThread?.carry_forward_hint || latestThread?.open_loop ? (
        <div className="mt-4 rounded-[1.2rem] border bg-slate-50/80 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Conversation memory</p>
          {latestThread?.continuity_memory ? <p className="mt-2 text-sm leading-6 text-slate-600">{latestThread.continuity_memory}</p> : null}
          {latestThread?.recent_change_hint ? <p className="mt-2 text-sm leading-6 text-slate-600">{latestThread.recent_change_hint}</p> : null}
          {latestThread?.carry_forward_hint ? <p className="mt-2 text-sm leading-6 text-slate-700">{latestThread.carry_forward_hint}</p> : null}
          {latestThread?.open_loop ? (
            <div className="mt-3 rounded-2xl border bg-white px-4 py-3">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Open loop</p>
              <p className="mt-2 text-sm leading-6 text-slate-700">{latestThread.open_loop}</p>
            </div>
          ) : null}
        </div>
      ) : null}
      {latestThread?.unresolved_hint ? (
        <div className="mt-4 rounded-[1.2rem] border bg-slate-50/80 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Still unresolved</p>
          <p className="mt-2 text-sm leading-6 text-slate-600">{latestThread.unresolved_hint}</p>
        </div>
      ) : null}
      {lead.relationship_recent_upload_summary ? (
        <div className="mt-4 rounded-[1.2rem] border bg-slate-50/80 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Fresh client context</p>
          <p className="mt-2 text-sm leading-6 text-slate-600">{lead.relationship_recent_upload_summary}</p>
          {lead.relationship_upload_follow_through_hint ? <p className="mt-3 text-sm leading-6 text-slate-700">{lead.relationship_upload_follow_through_hint}</p> : null}
          {lead.relationship_meeting_prep_summary ? (
            <div className="mt-3 rounded-2xl border bg-white px-4 py-3">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Use it in the next touch</p>
              <p className="mt-2 text-sm leading-6 text-slate-700">{lead.relationship_meeting_prep_summary}</p>
            </div>
          ) : null}
          <div className="mt-4 flex flex-wrap gap-3">
            <Button
              type="button"
              variant="outline"
              disabled={isDrafting}
              onClick={() =>
                onDraftAction({
                  objective: shouldReconnect ? "revive" : "follow_up",
                  tone: "warm",
                  length: "short",
                  status: shouldReconnect ? "Drafting a reconnect from fresh client context..." : "Drafting a reply from fresh client context...",
                })
              }
            >
              {shouldReconnect ? "Turn this into a reconnect" : "Turn this into a note"}
            </Button>
          </div>
        </div>
      ) : null}
      {shouldReconnect ? (
        <div className="mt-4 rounded-[1.2rem] border bg-slate-50/80 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Gentle re-entry</p>
          <p className="mt-2 text-sm leading-6 text-slate-600">{lead.relationship_reconnect_why_now || lead.relationship_timing_nudge}</p>
          {lead.relationship_reconnect_next_move ? (
            <div className="mt-3 rounded-2xl border bg-white px-4 py-3">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Next move</p>
              <p className="mt-2 text-sm leading-6 text-slate-700">{lead.relationship_reconnect_next_move}</p>
            </div>
          ) : null}
          <p className="mt-3 text-sm leading-6 text-slate-700">{lead.relationship_reconnect_message_hint || "Keep it warm, brief, and easy to answer."}</p>
        </div>
      ) : null}
      <div className="mt-4 flex flex-wrap gap-3">
        <Button disabled={isDrafting} onClick={() => onDraftAction(primaryAction.draft)}>
          {isDrafting ? "Drafting..." : primaryAction.label}
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
  const [shareStatus, setShareStatus] = useState<string | null>(null);
  const shareLink = intakeChannel?.magic_link_url ?? "";
  const shareMessage = shareLink
    ? `Send any screenshot, whiteboard photo, or handwritten note here whenever you have an update: ${shareLink}`
    : "";

  async function copyText(value: string, successMessage: string) {
    if (!value) {
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
      setShareStatus(successMessage);
    } catch {
      setShareStatus("Copy did not work in this browser. You can still copy the link manually.");
    }
  }

  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Client dropzone</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">Give clients an easy place to send updates.</h2>
      <p className="mt-3 text-sm leading-6 text-slate-600">
        Brivoly gives you one simple no-login page for screenshots, whiteboard photos, and note images. Save the defaults once, then reuse the same link whenever something changes.
      </p>

      {!advancedAiUnlocked ? (
        <div className="mt-5 rounded-[1.3rem] border border-amber-200 bg-amber-50 px-4 py-4 text-sm leading-6 text-amber-900">
          Shared image capture uses the same paid AI layer as advanced spreadsheet and file interpretation.
        </div>
      ) : null}

      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <div className="rounded-[1.3rem] border bg-slate-50 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">What clients can send</p>
          <p className="mt-2 text-sm leading-6 text-slate-700">
            Screenshot updates, whiteboard photos, handwritten notes, or other quick visual context that would otherwise get lost in text threads.
          </p>
        </div>
        <div className="rounded-[1.3rem] border bg-slate-50 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">What Brivoly does next</p>
          <p className="mt-2 text-sm leading-6 text-slate-700">
            Brivoly attaches the update to the right relationship memory so you can reopen the context later without hunting through email or messages.
          </p>
        </div>
      </div>

      <div className="mt-5 rounded-[1.3rem] border bg-slate-50 px-4 py-4">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Ready to share</p>
        <p className="mt-2 text-sm font-medium text-slate-900">
          {intakeChannel?.magic_link_url ? "Your client link is ready." : "The client link is not ready yet."}
        </p>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          {intakeChannel?.instructions ?? "Turn this on once so clients have a phone-friendly page they can keep using whenever something changes."}
        </p>
        {normalizedChannels.length ? (
          <p className="mt-3 text-sm text-slate-700">
            Usual ways clients send updates here: <span className="font-medium">{normalizedChannels.join(", ")}</span>
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
            <div className="mt-4 flex flex-wrap gap-2">
              <Button type="button" variant="outline" onClick={() => copyText(shareLink, "Client link copied.")}>
                Copy link
              </Button>
              <Button type="button" variant="outline" onClick={() => copyText(shareMessage, "Client share note copied.")}>
                Copy share note
              </Button>
            </div>
            <p className="mt-3 text-xs text-slate-500">Share the link once, then keep reusing it. No login is required.</p>
            {shareStatus ? <p className="mt-2 text-sm text-slate-600">{shareStatus}</p> : null}
          </>
        ) : null}
      </div>
    </section>
  );
}

function IntakeTaskNav({ activeTask }: { activeTask: CRMIntakeTask }) {
  const items: Array<{ href: string; title: string; body: string; task: CRMIntakeTask }> = [
    { href: "/clientos/intake", title: "Overview", body: "See the default flow at a glance.", task: "hub" },
    { href: "/clientos/intake/profile", title: "Usual formats", body: "Show what clients usually send.", task: "profile" },
    { href: "/clientos/intake/routing", title: "Usual path", body: "Choose the easiest way in once.", task: "routing" },
    { href: "/clientos/intake/capture", title: "Share link", body: "Keep one phone-friendly page ready.", task: "capture" },
  ];

  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-5 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Client dropzone</p>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
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
    <section className="grid gap-6 md:grid-cols-2">
      <TaskSummaryCard
        href="/clientos/intake/profile"
        eyebrow="Step 1"
        title="Show the kinds of updates you usually get"
        body={advancedAiUnlocked ? "Your AI memory defaults are ready. Keep them close to what clients actually send." : "Unlock the paid AI layer before relying on note images and messy files to carry client context back in."}
      />
      <TaskSummaryCard
        href="/clientos/intake/routing"
        eyebrow="Step 2"
        title="Choose the easiest path"
        body={normalizedChannels.length ? `Usual paths are ready: ${normalizedChannels.join(", ")}.` : "Set one path and one short note so sending updates feels obvious."}
      />
      <TaskSummaryCard
        href="/clientos/intake/capture"
        eyebrow="Step 3"
        title="Share the update link"
        body={hasMagicLink ? "A signed no-login page is live and ready to reuse with clients." : "Turn this on once so clients can send updates from their phone without friction."}
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
    <Link href={href} className="block min-w-0 overflow-hidden rounded-[1.75rem] border bg-white/90 p-6 shadow-sm transition hover:border-slate-400 hover:bg-white">
      <p className="break-words text-xs font-semibold uppercase tracking-[0.18em] text-slate-400 [overflow-wrap:anywhere] sm:tracking-[0.24em]">{eyebrow}</p>
      <h3 className="mt-3 break-words text-2xl font-semibold tracking-tight text-slate-950 [overflow-wrap:anywhere]">{title}</h3>
      <p className="mt-3 break-words text-sm leading-6 text-slate-600 [overflow-wrap:anywhere]">{body}</p>
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
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Usual path</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">Set the easiest path once.</h2>
      <p className="mt-3 text-sm leading-6 text-slate-600">
        Keep this simple: choose the usual paths for this account and leave one short note so every new update lands in the right place.
      </p>

      <div className="mt-5 space-y-4">
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Usual ways in</span>
          <input
            value={channelsDraft}
            onChange={(event) => onChannelsDraftChange(event.target.value)}
            placeholder="upload, magic_link, email"
            className="mt-2 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400 focus:bg-white"
          />
        </label>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => {
              onChannelsDraftChange("upload, magic_link, email");
              onRoutingNotesDraftChange(
                "Use the shared link for screenshots and quick updates. Use email when a client sends a longer file, thread, or fuller project context.",
              );
            }}
            className="rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-600 transition hover:border-slate-400 hover:text-slate-900"
          >
            Use recommended path
          </button>
          {[
            { label: "Shared link + email", value: "upload, magic_link, email" },
            { label: "Shared link + WhatsApp", value: "upload, magic_link, whatsapp" },
          ].map((preset) => (
            <button
              key={preset.label}
              type="button"
              onClick={() => onChannelsDraftChange(preset.value)}
              className="rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-600 transition hover:border-slate-400 hover:text-slate-900"
            >
              {preset.label}
            </button>
          ))}
          <button
            type="button"
            onClick={() =>
              onRoutingNotesDraftChange(
                "Use the shared link for screenshots and quick updates. Use email when a client sends a longer file, thread, or fuller project context.",
              )
            }
            className="rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-600 transition hover:border-slate-400 hover:text-slate-900"
          >
            Use recommended note
          </button>
        </div>
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">One short note</span>
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
          {isSaving ? "Saving..." : "Save defaults"}
        </Button>
        {saveStatus ? <p className="text-sm text-slate-500">{saveStatus}</p> : null}
      </div>
      {!canPersistSettings ? <p className="mt-3 text-sm text-slate-500">These defaults will appear once your account details finish loading.</p> : null}
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
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Usual client formats</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">Show Brivoly what clients usually send.</h2>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            Keep a short memory cue and your usual source formats here so future spreadsheet, file, and image interpretation stays close to how you actually work.
          </p>
        </div>
        <div className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] ${advancedAiUnlocked ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-amber-200 bg-amber-50 text-amber-800"}`}>
          {advancedAiUnlocked ? "Advanced AI unlocked" : "Advanced AI paywalled"}
        </div>
      </div>

      {!advancedAiUnlocked ? (
        <div className="mt-5 rounded-[1.3rem] border border-amber-200 bg-amber-50 px-4 py-4 text-sm leading-6 text-amber-900">
          AI-assisted file, spreadsheet, and image interpretation stays behind a paid plan. Current billing status: {formatBillingStatusLabel(billingStatus)}.
        </div>
      ) : null}

      <div className="mt-5 space-y-4">
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Usual formats</span>
          <input
            value={aiFormatsDraft}
            onChange={(event) => onAiFormatsDraftChange(event.target.value)}
            placeholder="csv, google_sheets, spreadsheet_screenshot, pdf_export"
            className="mt-2 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400 focus:bg-white"
          />
        </label>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => {
              onAiFormatsDraftChange("csv, google_sheets, spreadsheet_screenshot");
              onAiPromptDraftChange(
                "Treat uploads and messy files as relationship context first. Pull out what changed, what matters now, and the clearest next touch without adding admin work.",
              );
            }}
            className="rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-600 transition hover:border-slate-400 hover:text-slate-900"
          >
            Use recommended formats
          </button>
          {[
            { label: "Sheets + screenshots", value: "csv, google_sheets, spreadsheet_screenshot" },
            { label: "Image-first", value: "spreadsheet_screenshot, whiteboard_photo, handwritten_note" },
            { label: "Ops-heavy", value: "csv, google_sheets, pdf_export, spreadsheet_screenshot" },
          ].map((preset) => (
            <button
              key={preset.label}
              type="button"
              onClick={() => onAiFormatsDraftChange(preset.value)}
              className="rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-600 transition hover:border-slate-400 hover:text-slate-900"
            >
              {preset.label}
            </button>
          ))}
          <button
            type="button"
            onClick={() =>
              onAiPromptDraftChange(
                "Treat uploads and messy files as relationship context first. Pull out what changed, what matters now, and the clearest next touch without adding admin work.",
              )
            }
            className="rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-600 transition hover:border-slate-400 hover:text-slate-900"
          >
            Use recommended prompt
          </button>
        </div>
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">What to notice</span>
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
          {isSaving ? "Saving..." : "Save defaults"}
        </Button>
        {saveStatus ? <p className="text-sm text-slate-500">{saveStatus}</p> : null}
      </div>
      {!canPersistSettings ? <p className="mt-3 text-sm text-slate-500">These defaults will appear once account settings finish loading.</p> : null}
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
      <div className="mt-5 grid gap-3 md:grid-cols-2">
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
      <div className="mt-3 grid gap-3 md:grid-cols-2">
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
  draftFocusToken,
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
  draftFocusToken: number;
  onEmailObjectiveChange: (value: CRMEmailDraft["objective"]) => void;
  onEmailToneChange: (value: CRMEmailDraft["tone"]) => void;
  onEmailLengthChange: (value: CRMEmailDraft["length"]) => void;
  onEmailSubjectDraftChange: (value: string) => void;
  onEmailBodyDraftChange: (value: string) => void;
  onGenerateEmailDraft: (overrides?: {
    objective?: CRMEmailDraft["objective"];
    tone?: CRMEmailDraft["tone"];
    length?: CRMEmailDraft["length"];
    status?: string;
  }) => void;
}) {
  const launchHref = buildMailtoHref(emailSubjectDraft, emailBodyDraft);
  const suggestedResponses = buildSuggestedResponsePresets(lead);
  const composerSectionRef = useRef<HTMLElement | null>(null);
  const [memoryView, setMemoryView] = useState<"overview" | "last_30_days" | "meeting_prep" | "recent_changes" | "recent_upload">("overview");
  const memoryPanels = [
    { value: "overview" as const, label: "What matters", body: lead.relationship_context_summary || lead.notes || "No summary yet." },
    { value: "last_30_days" as const, label: "Last 30 days", body: lead.relationship_last_30_days_summary || "No 30-day summary yet." },
    { value: "meeting_prep" as const, label: "Meeting prep", body: lead.relationship_meeting_prep_summary || "No meeting prep summary yet." },
    { value: "recent_changes" as const, label: "What changed", body: lead.relationship_recent_changes_summary || "No recent changes were captured yet." },
    ...(lead.relationship_recent_upload_summary
      ? [
          {
            value: "recent_upload" as const,
            label: "Client-shared context",
            body: lead.relationship_recent_upload_summary,
          },
        ]
      : []),
  ];
  const activeMemoryPanel = memoryPanels.find((item) => item.value === memoryView) ?? memoryPanels[0];

  useEffect(() => {
    if (!draftFocusToken) {
      return;
    }
    composerSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [draftFocusToken, lead.id]);

  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Relationship memory</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">{lead.lead_name}</h2>
      <p className="mt-1 text-sm text-slate-600">{lead.company_name}</p>

      <div className="mt-5 grid gap-3 md:grid-cols-2">
        <TimelineTile label="Where it stands" value={formatStageLabel(lead.stage)} />
        <TimelineTile label="Best channel" value={lead.contact_channel} />
        <TimelineTile label="Point person" value={lead.owner_name} />
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <TimelineTile label="Last meaningful interaction" value={formatDateTime(lead.last_meaningful_interaction_at)} />
        <TimelineTile label="Relationship state" value={formatRelationshipState(lead.relationship_state)} />
        <TimelineTile
          label="Brivoly nudge"
          value={lead.relationship_upload_follow_through_hint || lead.relationship_timing_nudge || "Brivoly is keeping the timing in view."}
        />
      </div>

      {isReconnectMoment(lead) ? (
        <section className="mt-6 rounded-[1.5rem] border bg-sky-50/70 p-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-2xl">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-700">Gentle re-entry</p>
              <h3 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">Reopen this relationship without sounding abrupt.</h3>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                Brivoly is surfacing a low-pressure path back in so you do not have to reconstruct the opening from scratch.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Button
                onClick={() =>
                  onGenerateEmailDraft({
                    objective: "revive",
                    tone: "warm",
                    length: "short",
                    status: "Drafting a gentle reconnect...",
                  })
                }
                disabled={isGeneratingEmail}
              >
                {isGeneratingEmail ? "Drafting..." : "Draft gentle reconnect"}
              </Button>
            </div>
          </div>
          <div className="mt-4 grid gap-3 lg:grid-cols-2">
            <TimelineTile label="Why now" value={lead.relationship_reconnect_why_now || lead.relationship_timing_nudge || "Brivoly is keeping a reconnect path ready."} />
            <TimelineTile label="Why it can still land" value={describeReconnectWindow(lead)} />
            <TimelineTile label="Best re-entry" value={lead.relationship_reconnect_next_move || lead.next_step} />
            <TimelineTile label="Starter line" value={buildReconnectStarterLine(lead)} />
          </div>
        </section>
      ) : null}

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
        <p className="ui-eyebrow">Relationship memory</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {memoryPanels.map((item) => (
            <button
              key={item.value}
              type="button"
              onClick={() => setMemoryView(item.value)}
              className={`rounded-full border px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] transition ${
                memoryView === item.value
                  ? "border-slate-900 bg-slate-950 text-white"
                  : "border-slate-200 bg-white text-slate-600 hover:border-slate-400 hover:text-slate-900"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div className="mt-4 rounded-[1.2rem] border bg-white px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{activeMemoryPanel.label}</p>
          <p className="mt-2 text-sm leading-6 text-slate-700">{activeMemoryPanel.body}</p>
        </div>
        <div className="mt-4 rounded-[1.2rem] border bg-white px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Context on hand</p>
          <p className="mt-2 text-sm leading-6 text-slate-700">{lead.notes}</p>
          {lead.relationship_recent_upload_summary ? (
            <div className="mt-4 rounded-[1rem] border bg-slate-50/80 px-4 py-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">Recent upload context</p>
              <p className="mt-2 text-sm leading-6 text-slate-700">{lead.relationship_recent_upload_summary}</p>
              {lead.relationship_upload_follow_through_hint ? <p className="mt-3 text-sm leading-6 text-slate-700">{lead.relationship_upload_follow_through_hint}</p> : null}
            </div>
          ) : null}
        </div>
        {lead.relationship_recent_upload_summary && memoryView !== "meeting_prep" ? (
          <div className="mt-4 rounded-[1.2rem] border bg-white px-4 py-4">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Meeting prep from fresh context</p>
            <p className="mt-2 text-sm leading-6 text-slate-700">{lead.relationship_meeting_prep_summary}</p>
          </div>
        ) : null}
      </section>

      <section ref={composerSectionRef} className="mt-6 rounded-[1.5rem] border bg-white p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="ui-eyebrow">Suggested next note</p>
            <h3 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">Draft the next note without starting from zero.</h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              Brivoly uses the latest context, suggested next touch, and your saved business profile to suggest a message you can edit before sending.
            </p>
          </div>
          <div className="rounded-[1.2rem] border bg-slate-50 px-4 py-3 text-sm text-slate-600 lg:max-w-xs">
            <p className="ui-eyebrow">Sent from</p>
            <p className="mt-2">
              Sender: <span className="font-medium text-slate-900">{settings?.outbound_sender_name || settings?.business_name || "Fallback defaults"}</span>
            </p>
          </div>
        </div>

        <div className="mt-5 rounded-[1.2rem] border bg-slate-50/80 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Ways to say it</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {suggestedResponses.map((item) => (
              <button
                key={item.label}
                type="button"
                onClick={() => {
                  onGenerateEmailDraft({
                    objective: item.objective,
                    tone: item.tone,
                    length: item.length,
                    status: `Drafting a ${item.label.toLowerCase()} message...`,
                  });
                }}
                className="rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-slate-700 transition hover:border-slate-400 hover:text-slate-950"
              >
                {item.label}
              </button>
            ))}
          </div>
          <p className="mt-3 text-xs text-slate-500">Pick the message shape that fits this moment, then edit before sending.</p>
        </div>

        <div className="mt-5 grid gap-4 xl:grid-cols-3">
          <label className="block">
            <span className="ui-eyebrow">Objective</span>
            <select
              value={emailObjective}
              onChange={(event) => onEmailObjectiveChange(event.target.value as CRMEmailDraft["objective"])}
              className="mt-2 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400 focus:bg-white"
            >
              <option value="follow_up">General note</option>
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
          <Button onClick={() => onGenerateEmailDraft()} disabled={isGeneratingEmail}>
            {isGeneratingEmail ? "Drafting..." : emailDraft ? "Refresh draft" : "Draft note"}
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
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Keep the memory current</p>
        <textarea
          value={noteDraft}
          onChange={(event) => onNoteDraftChange(event.target.value)}
          placeholder="Capture what changed, what matters, or what you will want to remember before the next touch."
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
          {lead.timeline.map((entry) => {
            const uploadContext = isUploadTimelineEntry(entry);
            return (
            <div
              key={entry.id}
              className={`rounded-[1.35rem] border p-4 ${
                uploadContext ? "border-sky-200 bg-sky-50/80" : "bg-slate-50/80"
              }`}
            >
              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <div className="flex flex-wrap items-center gap-2">
                  <p className={`text-xs font-semibold uppercase tracking-[0.2em] ${uploadContext ? "text-sky-700" : "text-slate-400"}`}>
                    {uploadContext ? "client-shared context" : `${entry.kind.replaceAll("_", " ")} · ${entry.channel}`}
                  </p>
                  {uploadContext ? <MiniFlag label={formatUploadHistorySource(entry)} tone="neutral" /> : null}
                </div>
                <p className="text-xs text-slate-500">{formatDateTime(entry.occurred_at)}</p>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-700">{entry.summary}</p>
            </div>
            );
          })}
        </div>
      </section>
    </section>
  );
}

function RelationshipSignalsPanel({ summary }: { summary: NonNullable<CRMFollowUpOverview["relationship_summary"]> }) {
  const needsAttention = summary.drifting_count + summary.stale_count + summary.at_risk_count;
  const warmMoments = summary.referral_reminder_count + summary.milestone_reminder_count;
  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Client momentum</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">A calmer read on which relationships are steady and which ones need warmth.</h2>
      <div className="mt-5 space-y-3">
        <TimelineTile
          label="Holding steady"
          value={`${summary.active_count + summary.warm_count} relationship${summary.active_count + summary.warm_count === 1 ? "" : "s"} still feel warm or active`}
        />
        <TimelineTile
          label="Needs attention"
          value={needsAttention ? `${needsAttention} relationship${needsAttention === 1 ? "" : "s"} may need a warmer touch soon` : "Nothing feels especially fragile right now"}
        />
        {warmMoments ? (
          <TimelineTile
            label="Thoughtful touchpoints"
            value={`${warmMoments} personal or referral moment${warmMoments === 1 ? "" : "s"} could help you reconnect naturally`}
          />
        ) : null}
      </div>
    </section>
  );
}

function WarmIntroGraphPanel({ summary }: { summary: NonNullable<CRMFollowUpOverview["relationship_summary"]> }) {
  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Warm ways back in</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">Know who can help you reopen a quiet relationship more naturally.</h2>
      <p className="mt-3 text-sm leading-6 text-slate-600">
        When a past intro or referral gives you a softer re-entry path, Brivoly keeps it close instead of leaving it buried in old notes.
      </p>
      <div className="mt-5 grid gap-3 md:grid-cols-2">
        {summary.warm_intro_connections.length ? (
          summary.warm_intro_connections.map((connection) => (
            <div key={`${connection.source_name}-${connection.target_lead_id}`} className="rounded-[1.2rem] border bg-slate-50/80 px-4 py-4">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{connection.source_name}</p>
              <p className="mt-2 text-sm text-slate-700">
                could help reopen <span className="font-medium text-slate-950">{connection.target_lead_name}</span> at {connection.target_company_name}
              </p>
              <p className="mt-2 text-xs text-slate-500">Best person to pick it up: {connection.owner_name}</p>
            </div>
          ))
        ) : (
          <div className="rounded-[1.2rem] border border-dashed bg-slate-50/80 px-4 py-4 text-sm text-slate-600">
            No warm intro links are mapped yet. When you save referral context on a relationship, Brivoly can turn it into a softer path back in later.
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
      className={`inline-flex max-w-full items-center rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] [overflow-wrap:anywhere] ${
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
    <div className={`min-w-0 overflow-hidden rounded-[1.4rem] border p-5 shadow-sm ${toneClass}`}>
      <p className="break-words text-xs font-semibold uppercase tracking-[0.14em] [overflow-wrap:anywhere] sm:tracking-[0.2em]">{label}</p>
      <p className="mt-3 break-words text-3xl font-semibold tracking-tight [overflow-wrap:anywhere]">{value}</p>
    </div>
  );
}

function CompactMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 overflow-hidden rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
      <p className="break-words text-xs font-semibold uppercase tracking-[0.14em] text-slate-400 [overflow-wrap:anywhere] sm:tracking-[0.18em]">{label}</p>
      <p className="mt-2 break-words text-xl font-semibold text-white [overflow-wrap:anywhere]">{value}</p>
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
    <div className={`min-w-0 overflow-hidden rounded-2xl border px-4 py-3 ${className}`}>
      <p className="break-words text-xs font-semibold uppercase tracking-[0.14em] [overflow-wrap:anywhere] sm:tracking-[0.18em]">{label}</p>
      <p className="mt-2 break-words text-xl font-semibold [overflow-wrap:anywhere]">{value}</p>
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
    <div className={`inline-flex max-w-full rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] [overflow-wrap:anywhere] sm:tracking-[0.2em] ${className}`}>
      {priority} priority
    </div>
  );
}

function TimelineTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 overflow-hidden rounded-2xl border bg-white px-4 py-3">
      <p className="break-words text-xs font-semibold uppercase tracking-[0.14em] text-slate-400 [overflow-wrap:anywhere] sm:tracking-[0.2em]">{label}</p>
      <p className="mt-2 break-words text-sm text-slate-700 [overflow-wrap:anywhere]">{value}</p>
    </div>
  );
}

function TimelineTileDark({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 overflow-hidden rounded-2xl border border-white/10 bg-slate-900/40 px-4 py-3">
      <p className="break-words text-xs font-semibold uppercase tracking-[0.14em] text-slate-400 [overflow-wrap:anywhere] sm:tracking-[0.2em]">{label}</p>
      <p className="mt-2 break-words text-sm text-slate-200 [overflow-wrap:anywhere]">{value}</p>
    </div>
  );
}

function summarizePriority(item: CRMLeadFollowUp) {
  if (item.recent_email_threads.some((thread) => thread.needs_reply)) {
    return `Reply to ${item.lead_name}`;
  }
  if (item.relationship_state === "stale") {
    return `Reconnect with ${item.lead_name}`;
  }
  if (item.relationship_state === "at_risk" || item.relationship_state === "drifting") {
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

function getLatestUploadContextEntry(item: CRMLeadFollowUp) {
  const timeline = [...item.timeline]
    .filter((entry) => entry.kind === "import" || entry.channel === "magic_link" || entry.channel === "image" || entry.channel === "telegram")
    .sort((left, right) => new Date(right.occurred_at).getTime() - new Date(left.occurred_at).getTime());
  return timeline[0] ?? null;
}

function getReplySummary(item: CRMLeadFollowUp) {
  const replyThread = item.recent_email_threads.find((thread) => thread.needs_reply);
  if (!replyThread) {
    return item.next_step;
  }
  return replyThread.snippet || item.next_step;
}

function getReplyThread(item: CRMLeadFollowUp) {
  return [...item.recent_email_threads]
    .filter((thread) => thread.needs_reply)
    .sort((left, right) => new Date(right.last_message_at).getTime() - new Date(left.last_message_at).getTime())[0] ?? null;
}

function compareReplyPriority(left: CRMLeadFollowUp, right: CRMLeadFollowUp) {
  return (getNewestThreadTimestamp(right) - getNewestThreadTimestamp(left)) || compareSoonestFollowUp(left, right);
}

function compareReconnectPriority(left: CRMLeadFollowUp, right: CRMLeadFollowUp) {
  return (
    relationshipStateUrgency(right.relationship_state) - relationshipStateUrgency(left.relationship_state) ||
    getLastMeaningfulTimestamp(left) - getLastMeaningfulTimestamp(right) ||
    compareSoonestFollowUp(left, right)
  );
}

function compareProposalPriority(left: CRMLeadFollowUp, right: CRMLeadFollowUp) {
  return (
    Number(right.priority === "high") - Number(left.priority === "high") ||
    compareSoonestFollowUp(left, right) ||
    getLastMeaningfulTimestamp(right) - getLastMeaningfulTimestamp(left)
  );
}

function compareFreshContextPriority(left: CRMLeadFollowUp, right: CRMLeadFollowUp) {
  return getLatestContextTimestamp(right) - getLatestContextTimestamp(left);
}

function compareRecentUploadPriority(left: CRMLeadFollowUp, right: CRMLeadFollowUp) {
  return getLatestUploadContextTimestamp(right) - getLatestUploadContextTimestamp(left);
}

function compareSoonestFollowUp(left: CRMLeadFollowUp, right: CRMLeadFollowUp) {
  return new Date(left.next_follow_up_at).getTime() - new Date(right.next_follow_up_at).getTime();
}

function getNewestThreadTimestamp(item: CRMLeadFollowUp) {
  return getNewestThreadTime(item) ? new Date(getNewestThreadTime(item) as string).getTime() : 0;
}

function getLastMeaningfulTimestamp(item: CRMLeadFollowUp) {
  return item.last_meaningful_interaction_at ? new Date(item.last_meaningful_interaction_at).getTime() : 0;
}

function getLatestContextTimestamp(item: CRMLeadFollowUp) {
  const latest = getLatestContextEntry(item);
  return latest ? new Date(latest.occurred_at).getTime() : 0;
}

function getLatestUploadContextTimestamp(item: CRMLeadFollowUp) {
  const latest = getLatestUploadContextEntry(item);
  return latest ? new Date(latest.occurred_at).getTime() : 0;
}

function hasFreshContext(item: CRMLeadFollowUp) {
  const latest = getLatestContextTimestamp(item);
  if (!latest) {
    return false;
  }
  return Date.now() - latest <= 1000 * 60 * 60 * 24 * 3;
}

function hasRecentUploadContext(item: CRMLeadFollowUp) {
  if (!item.relationship_recent_upload_summary) {
    return false;
  }
  const latest = getLatestUploadContextTimestamp(item);
  if (!latest) {
    return false;
  }
  return Date.now() - latest <= 1000 * 60 * 60 * 24 * 3;
}

function relationshipStateUrgency(state: string) {
  if (state === "stale") {
    return 3;
  }
  if (state === "at_risk") {
    return 2;
  }
  if (state === "drifting") {
    return 1;
  }
  return 0;
}

function compareAttentionPriority(left: CRMLeadFollowUp, right: CRMLeadFollowUp) {
  return (
    Number(right.recent_email_threads.some((thread) => thread.needs_reply)) - Number(left.recent_email_threads.some((thread) => thread.needs_reply)) ||
    relationshipStateUrgency(right.relationship_state) - relationshipStateUrgency(left.relationship_state) ||
    compareSoonestFollowUp(left, right) ||
    getLastMeaningfulTimestamp(left) - getLastMeaningfulTimestamp(right)
  );
}

function matchesInboxThread(
  item: {
    leadName: string;
    companyName: string;
    thread: {
      subject: string;
      counterpart_email: string;
      counterpart_name: string;
      snippet: string;
      memory_summary: string;
      next_touch_hint: string;
      open_loop: string;
      relationship_pulse: string;
      recent_change_hint: string;
      continuity_span: string;
      carry_forward_hint: string;
      unresolved_hint: string;
      continuity_memory: string;
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
      item.thread.subject,
      item.thread.counterpart_email,
      item.thread.counterpart_name,
      item.thread.snippet,
      item.thread.memory_summary,
      item.thread.next_touch_hint,
      item.thread.open_loop,
      item.thread.relationship_pulse,
      item.thread.recent_change_hint,
      item.thread.continuity_span,
      item.thread.carry_forward_hint,
      item.thread.unresolved_hint,
      item.thread.continuity_memory,
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
    return item.relationship_state === "stale";
  }
  return item.relationship_state === "at_risk" || item.relationship_state === "drifting";
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

function formatRelationshipState(value: string) {
  return value.replaceAll("_", " ");
}

function buildSuggestedResponsePresets(lead: CRMLeadFollowUp) {
  const presets: Array<{
    label: string;
    objective: CRMEmailDraft["objective"];
    tone: CRMEmailDraft["tone"];
    length: CRMEmailDraft["length"];
  }> = [];

  const hasReplyPressure = lead.recent_email_threads.some((thread) => thread.needs_reply);
  const isProposalMoment = lead.stage.trim().toLowerCase() === "proposal";
  const isReconnectionMoment = isReconnectMoment(lead);

  if (hasReplyPressure) {
    presets.push({ label: "Reply", objective: "follow_up", tone: "warm", length: "short" });
    presets.push({ label: "Schedule", objective: "follow_up", tone: "direct", length: "short" });
  }
  if (isProposalMoment) {
    presets.push({ label: "Proposal nudge", objective: "follow_up", tone: "confident", length: "short" });
    presets.push({ label: "Send recap", objective: "recap", tone: "warm", length: "medium" });
  }
  if (isReconnectionMoment) {
    presets.push({ label: "Reconnect", objective: "revive", tone: "warm", length: "short" });
  }

  presets.push({ label: "Recap", objective: "recap", tone: "warm", length: "medium" });
  presets.push({ label: "Close loop", objective: "close_loop", tone: "direct", length: "short" });

  const seen = new Set<string>();
  return presets.filter((item) => {
    if (seen.has(item.label)) {
      return false;
    }
    seen.add(item.label);
    return true;
  });
}

function isReconnectMoment(lead: CRMLeadFollowUp) {
  return lead.relationship_state === "stale" || lead.relationship_state === "drifting" || lead.relationship_state === "at_risk";
}

function describeReconnectWindow(lead: CRMLeadFollowUp) {
  if (lead.referral_source_name) {
    return `There is still a warmer path here through ${lead.referral_source_name}.`;
  }
  if (lead.relationship_recent_upload_summary) {
    return "Fresh client context gives you a natural reason to step back in.";
  }
  if (lead.recent_email_threads.some((thread) => thread.continuity_memory || thread.carry_forward_hint || thread.unresolved_hint)) {
    return "Brivoly is still holding enough thread context that you do not need to reopen this cold.";
  }
  if (lead.relationship_reminders.length) {
    return "A personal or company moment gives this a softer reason to reopen now.";
  }
  if (lead.last_meaningful_interaction_at) {
    return "There is still enough recent context to make a brief check-in feel natural.";
  }
  return "Keep it light and simple. Brivoly will hold the context you do have.";
}

function buildReconnectStarterLine(lead: CRMLeadFollowUp) {
  if (lead.relationship_reconnect_message_hint) {
    return lead.relationship_reconnect_message_hint;
  }
  if (lead.relationship_recent_upload_summary) {
    return "Wanted to circle back while the new context you sent is still fresh.";
  }
  if (lead.relationship_reminders[0]?.message) {
    return `Wanted to check back in while ${lead.relationship_reminders[0].message.toLowerCase()}`;
  }
  if (lead.last_meaningful_interaction_at) {
    return "Wanted to check back in and make the next step easy from here.";
  }
  return "Wanted to reconnect and see if this is worth picking back up.";
}

function formatReminderKind(value: string) {
  return value.replaceAll("_", " ");
}

function isUploadTimelineEntry(entry: CRMLeadFollowUp["timeline"][number]) {
  const normalizedChannel = entry.channel.trim().toLowerCase();
  return entry.kind === "import" || normalizedChannel === "magic_link" || normalizedChannel === "image" || normalizedChannel === "telegram";
}

function formatUploadHistorySource(entry: CRMLeadFollowUp["timeline"][number]) {
  const normalizedChannel = entry.channel.trim().toLowerCase();
  if (normalizedChannel === "magic_link") {
    return "shared link";
  }
  if (normalizedChannel === "telegram") {
    return "phone upload";
  }
  if (normalizedChannel === "image") {
    return "image";
  }
  return "imported";
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
