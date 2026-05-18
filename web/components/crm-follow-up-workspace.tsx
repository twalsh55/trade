"use client";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  useDeferredValue,
  useEffect,
  useRef,
  useState,
  useTransition,
} from "react";

import { BusinessProfileOnboarding } from "@/components/settings/business-profile-onboarding";
import { Button } from "@/components/ui/button";
import type {
  AccountSettings,
  BillingOverview,
  CRMCalendarConnection,
  CRMEmailDraft,
  CRMFollowUpOverview,
  CRMImportHeaderMapping,
  CRMImportClarificationQuestion,
  CRMImportPreview,
  CRMImportPreviewRow,
  CRMLeadFollowUp,
  CRMMailboxConnection,
  CRMPipelineStageSummary,
  CRMRelationshipReminder,
  CRMRemoteIntakeChannel,
} from "@/lib/types";

export type CRMWorkspaceView =
  | "overview"
  | "followups"
  | "inbox"
  | "pipeline"
  | "import"
  | "intake";
type CRMIntakeTask = "hub" | "profile" | "routing" | "capture";
type RelationshipFilter =
  | "all"
  | "due"
  | "reply"
  | "fresh_context"
  | "open_loop"
  | "stale"
  | "at_risk";
type InboxFilter =
  | "all"
  | "reply"
  | "waiting"
  | "quiet"
  | "unresolved"
  | "long_thread"
  | "new_from_inbox";
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
  memoryView?: "meeting_prep";
  actionLabel?: string;
  onAction?: () => void;
};
type TodayFocusMove = {
  id: string;
  label: string;
  title: string;
  body: string;
  actionLabel: string;
  onAction: () => void;
};
type TodayRhythmStep = {
  id: string;
  label: string;
  title: string;
  body: string;
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
  const searchParams = useSearchParams();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const mailboxSectionRef = useRef<HTMLElement | null>(null);
  const calendarSectionRef = useRef<HTMLElement | null>(null);
  const [overview, setOverview] = useState(initialOverview);
  const [settings, setSettings] = useState<AccountSettings | null>(
    initialSettings,
  );
  const [selectedLeadId, setSelectedLeadId] = useState(
    initialOverview.items[0]?.id ?? null,
  );
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [noteDraft, setNoteDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [relationshipQuery, setRelationshipQuery] = useState("");
  const [relationshipFilter, setRelationshipFilter] =
    useState<RelationshipFilter>("all");
  const [sourceType, setSourceType] = useState<"file_upload" | "google_sheets">(
    "file_upload",
  );
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [sheetUrl, setSheetUrl] = useState("");
  const [importPreview, setImportPreview] = useState<CRMImportPreview | null>(
    null,
  );
  const [importFieldMapping, setImportFieldMapping] = useState<
    Record<string, string>
  >({});
  const [clarificationAnswers, setClarificationAnswers] = useState<
    Record<string, string>
  >({});
  const [rowOverrides, setRowOverrides] = useState<
    Record<string, Record<string, string>>
  >({});
  const [isImportMappingDirty, setIsImportMappingDirty] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [importStatus, setImportStatus] = useState<string | null>(null);
  const [aiPromptDraft, setAiPromptDraft] = useState(
    initialSettings?.crm_ai_prompt ?? "",
  );
  const [aiFormatsDraft, setAiFormatsDraft] = useState(
    (initialSettings?.crm_preferred_import_formats ?? []).join(", "),
  );
  const [aiSettingsStatus, setAiSettingsStatus] = useState<string | null>(null);
  const [routingChannelsDraft, setRoutingChannelsDraft] = useState(
    (initialSettings?.crm_image_intake_channels ?? []).join(", "),
  );
  const [routingNotesDraft, setRoutingNotesDraft] = useState(
    initialSettings?.crm_image_intake_notes ?? "",
  );
  const [routingSettingsStatus, setRoutingSettingsStatus] = useState<
    string | null
  >(null);
  const [emailObjective, setEmailObjective] =
    useState<CRMEmailDraft["objective"]>("follow_up");
  const [emailTone, setEmailTone] = useState<CRMEmailDraft["tone"]>("warm");
  const [emailLength, setEmailLength] =
    useState<CRMEmailDraft["length"]>("short");
  const [emailDraft, setEmailDraft] = useState<CRMEmailDraft | null>(null);
  const [emailSubjectDraft, setEmailSubjectDraft] = useState("");
  const [emailBodyDraft, setEmailBodyDraft] = useState("");
  const [emailStatus, setEmailStatus] = useState<string | null>(null);
  const [inboxThreadId, setInboxThreadId] = useState("");
  const [inboxSource, setInboxSource] = useState("gmail");
  const [inboxDirection, setInboxDirection] = useState<"inbound" | "outbound">(
    "inbound",
  );
  const [inboxCounterpartName, setInboxCounterpartName] = useState("");
  const [inboxCounterpartEmail, setInboxCounterpartEmail] = useState("");
  const [inboxSubject, setInboxSubject] = useState("");
  const [inboxMessageBody, setInboxMessageBody] = useState("");
  const [inboxStatus, setInboxStatus] = useState<string | null>(null);
  const [mailboxConnections, setMailboxConnections] = useState<
    CRMMailboxConnection[]
  >([]);
  const [calendarConnections, setCalendarConnections] = useState<
    CRMCalendarConnection[]
  >([]);
  const [mailboxProvider, setMailboxProvider] = useState<"gmail" | "outlook">(
    "gmail",
  );
  const [mailboxEmail, setMailboxEmail] = useState("");
  const [mailboxDisplayName, setMailboxDisplayName] = useState("");
  const [mailboxStatus, setMailboxStatus] = useState<string | null>(null);
  const [calendarProvider, setCalendarProvider] = useState<
    "google_calendar" | "outlook_calendar"
  >("google_calendar");
  const [calendarAddress, setCalendarAddress] = useState("");
  const [calendarDisplayName, setCalendarDisplayName] = useState("");
  const [calendarStatus, setCalendarStatus] = useState<string | null>(null);
  const [calendarEventTitle, setCalendarEventTitle] = useState("");
  const [calendarEventStartsAt, setCalendarEventStartsAt] = useState("");
  const [calendarAttendeeEmails, setCalendarAttendeeEmails] = useState("");
  const [calendarEventNotes, setCalendarEventNotes] = useState("");
  const [inboxQuery, setInboxQuery] = useState("");
  const [inboxFilter, setInboxFilter] = useState<InboxFilter>("all");
  const [isPending, startTransition] = useTransition();
  const [isImportPending, startImportTransition] = useTransition();
  const [isAiSettingsPending, startAiSettingsTransition] = useTransition();
  const [isEmailPending, startEmailTransition] = useTransition();
  const [isInboxPending, startInboxTransition] = useTransition();
  const [isMailboxPending, startMailboxTransition] = useTransition();
  const [isCalendarPending, startCalendarTransition] = useTransition();
  const [queuedTodayDraft, setQueuedTodayDraft] = useState<{
    leadId: string;
    preset: TodayDraftPreset;
  } | null>(null);
  const [draftFocusToken, setDraftFocusToken] = useState(0);
  const deferredRelationshipQuery = useDeferredValue(relationshipQuery);
  const deferredInboxQuery = useDeferredValue(inboxQuery);
  const resetImportWorkspace = (
    nextSourceType?: "file_upload" | "google_sheets",
  ) => {
    if (nextSourceType) {
      setSourceType(nextSourceType);
    }
    setSelectedFile(null);
    setSheetUrl("");
    setImportPreview(null);
    setImportFieldMapping({});
    setClarificationAnswers({});
    setRowOverrides({});
    setIsImportMappingDirty(false);
    setImportStatus(null);
    setImportError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };
  const hasImportWorkspaceState = Boolean(
    selectedFile ||
      sheetUrl.trim() ||
      importPreview ||
      importStatus ||
      importError,
  );

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

  const filteredFollowUps = overview.items.filter(
    (item) =>
      matchesRelationshipQuery(item, deferredRelationshipQuery) &&
      matchesRelationshipFilter(item, relationshipFilter),
  );
  const selectedLead =
    filteredFollowUps.find((item) => item.id === selectedLeadId) ??
    filteredFollowUps[0] ??
    null;
  const selectedThread =
    selectedLead?.recent_email_threads.find(
      (thread) => thread.thread_id === selectedThreadId,
    ) ?? null;
  const preferredMailboxConnection =
    (selectedThread
      ? mailboxConnections.find(
          (connection) =>
            connection.status === "connected" &&
            connection.provider === selectedThread.source,
        )
      : null) ??
    mailboxConnections.find(
      (connection) => connection.status === "connected",
    ) ??
    null;
  const advancedAiUnlocked = hasAdvancedAiAccess(initialBilling);
  const showingOverview = view === "overview";
  const showingFollowups = view === "followups";
  const showingInbox = view === "inbox";
  const showingPipeline = view === "pipeline";
  const showingImport = view === "import";
  const showingIntake = view === "intake";
  const intakeTask = resolveIntakeTask(pathname ?? "/clientos/intake");
  const requestedLeadId = searchParams?.get("lead");
  const requestedMemoryView =
    searchParams?.get("memory") === "meeting_prep" ? "meeting_prep" : null;
  const requestedConnectionFocus = searchParams?.get("connections");
  const ambientConnectionFocus =
    overview.ambient_memory_summary?.suggested_action_focus || "";
  const ambientActionKind =
    overview.ambient_memory_summary?.suggested_action_kind || "";
  const connectionFocus =
    requestedConnectionFocus === "mailbox" ||
    requestedConnectionFocus === "calendar" ||
    requestedConnectionFocus === "all"
      ? requestedConnectionFocus
      : ambientConnectionFocus === "mailbox" ||
          ambientConnectionFocus === "calendar" ||
          ambientConnectionFocus === "all"
        ? ambientConnectionFocus
        : null;

  const emphasizedActionClass =
    "border-slate-900 bg-slate-950 text-white hover:bg-slate-800 hover:text-white";

  useEffect(() => {
    if (
      view !== "followups" ||
      !queuedTodayDraft ||
      !selectedLead ||
      selectedLead.id !== queuedTodayDraft.leadId
    ) {
      return;
    }
    generateEmailDraftForLead(selectedLead, queuedTodayDraft.preset);
    setQueuedTodayDraft(null);
  }, [queuedTodayDraft, selectedLead, view]);

  useEffect(() => {
    setAiPromptDraft(initialSettings?.crm_ai_prompt ?? "");
    setAiFormatsDraft(
      (initialSettings?.crm_preferred_import_formats ?? []).join(", "),
    );
    setRoutingChannelsDraft(
      (initialSettings?.crm_image_intake_channels ?? []).join(", "),
    );
    setRoutingNotesDraft(initialSettings?.crm_image_intake_notes ?? "");
  }, [initialSettings]);

  useEffect(() => {
    if (!filteredFollowUps.some((item) => item.id === selectedLeadId)) {
      setSelectedLeadId(filteredFollowUps[0]?.id ?? null);
    }
  }, [filteredFollowUps, selectedLeadId]);

  useEffect(() => {
    if (!selectedLead) {
      setSelectedThreadId(null);
      return;
    }
    if (
      selectedThreadId &&
      selectedLead.recent_email_threads.some(
        (thread) => thread.thread_id === selectedThreadId,
      )
    ) {
      return;
    }
    setSelectedThreadId(
      selectedLead.recent_email_threads[0]?.thread_id ?? null,
    );
  }, [selectedLead, selectedThreadId]);

  useEffect(() => {
    if (!requestedLeadId) {
      return;
    }
    if (overview.items.some((item) => item.id === requestedLeadId)) {
      setSelectedLeadId(requestedLeadId);
    }
  }, [overview.items, requestedLeadId]);

  useEffect(() => {
    let cancelled = false;

    async function loadMailboxConnections() {
      try {
        const response = await fetch("/api/crm/inbox/mailboxes", {
          cache: "no-store",
        });
        const body = (await response.json().catch(() => null)) as {
          items?: CRMMailboxConnection[];
          error?: string;
        } | null;
        if (!response.ok || !body?.items) {
          throw new Error(body?.error || "Unable to load mailbox connections.");
        }
        if (!cancelled) {
          setMailboxConnections(body.items);
        }
      } catch (mailboxError) {
        if (!cancelled) {
          setMailboxStatus(
            mailboxError instanceof Error
              ? mailboxError.message
              : "Unable to load mailbox connections.",
          );
        }
      }
    }

    void loadMailboxConnections();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadCalendarConnections() {
      try {
        const response = await fetch("/api/crm/calendars", {
          cache: "no-store",
        });
        const body = (await response.json().catch(() => null)) as {
          items?: CRMCalendarConnection[];
          error?: string;
        } | null;
        if (!response.ok || !body?.items) {
          throw new Error(
            body?.error || "Unable to load calendar connections.",
          );
        }
        if (!cancelled) {
          setCalendarConnections(body.items);
        }
      } catch (calendarError) {
        if (!cancelled) {
          setCalendarStatus(
            calendarError instanceof Error
              ? calendarError.message
              : "Unable to load calendar connections.",
          );
        }
      }
    }

    void loadCalendarConnections();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (searchParams?.get("mailbox") === "connected") {
      setMailboxStatus(
        "Mailbox connected. Brivoly can now keep relationship memory fresh from that inbox.",
      );
      router.replace(
        view === "inbox" ? "/clientos/inbox" : (pathname ?? "/clientos/inbox"),
      );
    }
  }, [pathname, router, searchParams, view]);

  useEffect(() => {
    if (view !== "inbox" || !connectionFocus) {
      return;
    }
    if (connectionFocus === "mailbox") {
      setMailboxStatus(
        (current) =>
          current ??
          "This is the inbox connection area Brivoly wants you to check next.",
      );
      mailboxSectionRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
      return;
    }
    if (connectionFocus === "calendar") {
      setCalendarStatus(
        (current) =>
          current ??
          "This is the calendar memory area Brivoly wants you to check next.",
      );
      calendarSectionRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
      return;
    }
    if (connectionFocus === "all") {
      mailboxSectionRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }
  }, [connectionFocus, view]);

  async function refreshAmbientMemory() {
    const [overviewResponse, mailboxResponse, calendarResponse] =
      await Promise.all([
        fetch("/api/crm/followups", { cache: "no-store" }),
        fetch("/api/crm/inbox/mailboxes", { cache: "no-store" }),
        fetch("/api/crm/calendars", { cache: "no-store" }),
      ]);

    const overviewBody = (await overviewResponse.json().catch(() => null)) as
      | CRMFollowUpOverview
      | { error?: string }
      | null;
    const mailboxBody = (await mailboxResponse.json().catch(() => null)) as {
      items?: CRMMailboxConnection[];
      error?: string;
    } | null;
    const calendarBody = (await calendarResponse.json().catch(() => null)) as {
      items?: CRMCalendarConnection[];
      error?: string;
    } | null;

    if (overviewResponse.ok && overviewBody && "items" in overviewBody) {
      setOverview(overviewBody);
      if (
        selectedLeadId &&
        !overviewBody.items.some((item) => item.id === selectedLeadId)
      ) {
        setSelectedLeadId(overviewBody.items[0]?.id ?? null);
      }
    }
    if (mailboxResponse.ok && mailboxBody?.items) {
      setMailboxConnections(mailboxBody.items);
    }
    if (calendarResponse.ok && calendarBody?.items) {
      setCalendarConnections(calendarBody.items);
    }
  }

  useEffect(() => {
    const shouldRefreshInBackground =
      showingOverview || showingInbox || showingPipeline || showingFollowups;
    const hasActiveBackgroundMemory =
      mailboxConnections.some(
        (connection) =>
          connection.background_sync_enabled &&
          connection.status === "connected",
      ) ||
      calendarConnections.some(
        (connection) =>
          connection.background_sync_enabled &&
          connection.status === "connected",
      );
    if (!shouldRefreshInBackground || !hasActiveBackgroundMemory) {
      return;
    }

    let cancelled = false;
    const runRefresh = async () => {
      if (cancelled) {
        return;
      }
      try {
        await refreshAmbientMemory();
      } catch {
        // Ambient refresh should stay quiet; explicit actions still surface their own errors.
      }
    };

    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void runRefresh();
      }
    }, 45000);

    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        void runRefresh();
      }
    };

    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [
    calendarConnections,
    mailboxConnections,
    selectedLeadId,
    showingFollowups,
    showingInbox,
    showingOverview,
    showingPipeline,
  ]);

  function runAction(
    followUpId: string,
    payload: {
      action: "complete" | "snooze" | "note";
      snooze_hours?: number;
      note_body?: string;
    },
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

        const data = (await response.json().catch(() => null)) as
          | CRMFollowUpOverview
          | { error?: string }
          | null;
        if (!response.ok || !data || !("items" in data)) {
          throw new Error(
            (data && "error" in data && data.error) ||
              "Unable to update follow-up.",
          );
        }

        setOverview(data);
        if (
          followUpId === selectedLeadId &&
          !data.items.some((item) => item.id === followUpId)
        ) {
          setSelectedLeadId(data.items[0]?.id ?? null);
        }
        afterSuccess?.();
        router.refresh();
      } catch (actionError) {
        setError(
          actionError instanceof Error
            ? actionError.message
            : "Unable to update follow-up.",
        );
      } finally {
        setPendingId(null);
      }
    });
  }

  function saveNote() {
    if (!selectedLead) {
      return;
    }
    runAction(selectedLead.id, { action: "note", note_body: noteDraft }, () =>
      setNoteDraft(""),
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
    const effectiveClarificationAnswers =
      answersOverride ?? clarificationAnswers;
    if (Object.keys(effectiveClarificationAnswers).length) {
      formData.set(
        "clarification_answers",
        JSON.stringify(effectiveClarificationAnswers),
      );
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
        throw new Error(
          "AI note image intake is available on active or trialing paid plans.",
        );
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
          buildImportFormData(
            answersOverride,
            mappingOverride,
            rowOverridesOverride,
          ),
        );
        setImportPreview(data);
        setImportFieldMapping(
          Object.fromEntries(
            data.header_mappings
              .filter((item) => item.mapped_field)
              .map((item) => [
                item.original_header,
                item.mapped_field as string,
              ]),
          ),
        );
        setClarificationAnswers((current) => {
          const activeQuestionIds = new Set(
            (data.clarification?.questions ?? []).map((item) => item.id),
          );
          if (!activeQuestionIds.size) {
            return {};
          }
          const nextAnswers = answersOverride ?? current;
          return Object.fromEntries(
            Object.entries(nextAnswers).filter(([key]) =>
              activeQuestionIds.has(key),
            ),
          );
        });
        setRowOverrides((current) =>
          Object.fromEntries(
            Object.entries(rowOverridesOverride ?? current).filter(
              ([rowNumber, fields]) =>
                data.rows.some((row) => String(row.row_number) === rowNumber) &&
                Object.keys(fields).length > 0,
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
          | {
              imported_count: number;
              skipped_duplicates: number;
              skipped_invalid: number;
              overview: CRMFollowUpOverview;
            }
          | { error?: string }
          | null;
        if (!response.ok || !data || !("overview" in data)) {
          throw new Error(
            (data && "error" in data && data.error) ||
              "Unable to import spreadsheet rows.",
          );
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
        setImportError(
          commitError instanceof Error
            ? commitError.message
            : "Unable to import spreadsheet rows.",
        );
      }
    });
  }

  function updateImportFieldMapping(header: string, field: string) {
    const nextMapping = {
      ...importFieldMapping,
      [header]: field,
    };
    setImportFieldMapping(nextMapping);
    setImportStatus(
      "Re-checking the preview with your updated column mapping...",
    );
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

  function updateRowOverride(
    rowNumber: number,
    fieldName: string,
    value: string,
  ) {
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
      setImportError(
        "Enter a next follow-up date before asking Brivoly to re-check that row.",
      );
      return;
    }
    setImportStatus("Re-checking the preview with your in-app row fix...");
    setIsImportMappingDirty(false);
    requestImportPreview(undefined, undefined, nextOverrides);
  }

  async function requestImportPreviewWithBestEffort(
    buildFormData: () => FormData,
  ) {
    let lastMessage =
      "Brivoly could not build the preview this time, but it kept the import staged so you can try again.";
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const response = await fetch("/api/crm/import/preview", {
        method: "POST",
        body: buildFormData(),
      });
      const data = (await response.json().catch(() => null)) as
        | CRMImportPreview
        | { error?: string }
        | null;
      if (response.ok && data && "rows" in data) {
        return data;
      }

      if (
        data &&
        "error" in data &&
        typeof data.error === "string" &&
        data.error.trim()
      ) {
        lastMessage = data.error.trim();
      } else if (!response.ok && attempt === 0 && response.status >= 500) {
        lastMessage =
          "Brivoly hit an import hiccup, so it retried the preview automatically. Please try once more if the sheet is still not visible.";
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
        const body = (await response.json().catch(() => null)) as
          | AccountSettings
          | { error?: string }
          | null;
        if (!response.ok || !body || !("benchmark" in body)) {
          throw new Error(
            (body && "error" in body && body.error) ||
              "Unable to save AI intake settings.",
          );
        }
        setSettings(body);
        setAiPromptDraft(body.crm_ai_prompt);
        setAiFormatsDraft(body.crm_preferred_import_formats.join(", "));
        setAiSettingsStatus("AI intake preferences saved.");
      } catch (saveError) {
        setAiSettingsStatus(
          saveError instanceof Error
            ? saveError.message
            : "Unable to save AI intake settings.",
        );
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
        const body = (await response.json().catch(() => null)) as
          | AccountSettings
          | { error?: string }
          | null;
        if (!response.ok || !body || !("benchmark" in body)) {
          throw new Error(
            (body && "error" in body && body.error) ||
              "Unable to save intake routing settings.",
          );
        }
        setSettings(body);
        setRoutingChannelsDraft(body.crm_image_intake_channels.join(", "));
        setRoutingNotesDraft(body.crm_image_intake_notes);
        setRoutingSettingsStatus("Intake routing preferences saved.");
      } catch (saveError) {
        setRoutingSettingsStatus(
          saveError instanceof Error
            ? saveError.message
            : "Unable to save intake routing settings.",
        );
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
        const response = await fetch(
          `/api/crm/followups/email-draft/${lead.id}`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              objective,
              tone,
              length,
            }),
          },
        );
        const body = (await response.json().catch(() => null)) as
          | CRMEmailDraft
          | { error?: string }
          | null;
        if (!response.ok || !body || !("subject" in body)) {
          throw new Error(
            (body && "error" in body && body.error) ||
              "Unable to generate an email draft.",
          );
        }
        setEmailDraft(body);
        setEmailSubjectDraft(body.subject);
        setEmailBodyDraft(body.body);
        setEmailStatus("Draft ready. Tweak anything before sending.");
      } catch (draftError) {
        setEmailStatus(
          draftError instanceof Error
            ? draftError.message
            : "Unable to generate an email draft.",
        );
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

  function focusLeadForFollowUp(leadId: string, threadId?: string | null) {
    setRelationshipQuery("");
    setRelationshipFilter("all");
    setSelectedLeadId(leadId);
    setSelectedThreadId(threadId ?? null);
  }

  function requestDraftFocus() {
    setDraftFocusToken((value) => value + 1);
  }

  function runTodayPriorityAction(
    leadId: string,
    route: string,
    preset?: TodayDraftPreset,
    memoryView?: "meeting_prep",
    threadId?: string | null,
  ) {
    focusLeadForFollowUp(leadId, threadId);
    if (preset) {
      requestDraftFocus();
      setQueuedTodayDraft({ leadId, preset });
    }
    const nextRoute =
      route === "/clientos/follow-ups" && memoryView
        ? `${route}?lead=${encodeURIComponent(leadId)}&memory=${encodeURIComponent(memoryView)}`
        : route;
    router.push(nextRoute);
  }

  function openAmbientMemoryAction(route: string) {
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
                    : settings?.outbound_sender_name ||
                      settings?.business_name ||
                      "Brivoly",
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
        const body = (await response.json().catch(() => null)) as
          | CRMFollowUpOverview
          | { error?: string }
          | null;
        if (!response.ok || !body || !("items" in body)) {
          throw new Error(
            (body && "error" in body && body.error) ||
              "Unable to sync the inbox thread.",
          );
        }
        setOverview(body);
        setSelectedLeadId(body.items[0]?.id ?? null);
        setInboxStatus(
          "Thread synced. Brivoly updated the relationship memory and follow-up queue.",
        );
        setInboxThreadId("");
        setInboxCounterpartName("");
        setInboxCounterpartEmail("");
        setInboxSubject("");
        setInboxMessageBody("");
        router.refresh();
      } catch (syncError) {
        setInboxStatus(
          syncError instanceof Error
            ? syncError.message
            : "Unable to sync the inbox thread.",
        );
      }
    });
  }

  function upsertMailboxConnection(connection: CRMMailboxConnection) {
    setMailboxConnections((current) => {
      const remaining = current.filter((item) => item.id !== connection.id);
      return [connection, ...remaining];
    });
  }

  function connectMailbox() {
    setMailboxStatus("Connecting the mailbox to Brivoly...");
    startMailboxTransition(async () => {
      try {
        const response = await fetch("/api/crm/inbox/mailboxes", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            provider: mailboxProvider,
            email_address: mailboxEmail.trim(),
            display_name: mailboxDisplayName.trim(),
          }),
        });
        const body = (await response.json().catch(() => null)) as
          | CRMMailboxConnection
          | { error?: string }
          | null;
        if (!response.ok || !body || !("id" in body)) {
          throw new Error(
            (body && "error" in body && body.error) ||
              "Unable to connect the mailbox right now.",
          );
        }
        upsertMailboxConnection(body);
        setMailboxStatus(
          `${body.provider === "gmail" ? "Gmail" : "Outlook"} is now connected as ${body.email_address}.`,
        );
        setMailboxEmail("");
        setMailboxDisplayName("");
      } catch (mailboxError) {
        setMailboxStatus(
          mailboxError instanceof Error
            ? mailboxError.message
            : "Unable to connect the mailbox right now.",
        );
      }
    });
  }

  function startMailboxOAuth(provider: "gmail" | "outlook") {
    setMailboxStatus(
      `Opening ${provider === "gmail" ? "Gmail" : "Outlook"} so you can connect the real mailbox...`,
    );
    startMailboxTransition(async () => {
      try {
        const response = await fetch("/api/crm/inbox/mailboxes/oauth/start", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ provider }),
        });
        const body = (await response.json().catch(() => null)) as {
          authorization_url?: string;
          error?: string;
        } | null;
        if (!response.ok || !body?.authorization_url) {
          throw new Error(
            body?.error || "Unable to begin the mailbox connection right now.",
          );
        }
        window.location.assign(body.authorization_url);
      } catch (mailboxError) {
        setMailboxStatus(
          mailboxError instanceof Error
            ? mailboxError.message
            : "Unable to begin the mailbox connection right now.",
        );
      }
    });
  }

  function syncMailboxConnection(connectionId: string) {
    setMailboxStatus("Pulling recent mailbox activity into Brivoly...");
    startMailboxTransition(async () => {
      try {
        const response = await fetch(
          `/api/crm/inbox/mailboxes/${connectionId}/sync`,
          { method: "POST" },
        );
        const body = (await response.json().catch(() => null)) as
          | {
              connection: CRMMailboxConnection;
              overview: CRMFollowUpOverview;
              synced_threads: number;
              created_contacts: number;
              updated_relationships: number;
            }
          | { error?: string }
          | null;
        if (!response.ok || !body || !("connection" in body)) {
          throw new Error(
            (body && "error" in body && body.error) ||
              "Unable to sync the mailbox right now.",
          );
        }
        setOverview(body.overview);
        upsertMailboxConnection(body.connection);
        setSelectedLeadId(
          (current) => current ?? body.overview.items[0]?.id ?? null,
        );
        setMailboxStatus(
          `Mailbox synced. ${body.synced_threads} thread${body.synced_threads === 1 ? "" : "s"} refreshed, ${body.created_contacts} relationship${body.created_contacts === 1 ? "" : "s"} created, and ${body.updated_relationships} updated.`,
        );
        router.refresh();
      } catch (mailboxError) {
        setMailboxStatus(
          mailboxError instanceof Error
            ? mailboxError.message
            : "Unable to sync the mailbox right now.",
        );
      }
    });
  }

  function renewMailboxWatch(connection: CRMMailboxConnection) {
    setMailboxStatus(
      `Refreshing provider watch coverage for ${connection.email_address}...`,
    );
    startMailboxTransition(async () => {
      try {
        const response = await fetch(
          `/api/crm/inbox/mailboxes/${connection.id}/watch`,
          { method: "POST" },
        );
        const body = (await response.json().catch(() => null)) as
          | CRMMailboxConnection
          | { error?: string }
          | null;
        if (!response.ok || !body || !("id" in body)) {
          throw new Error(
            (body && "error" in body && body.error) ||
              "Unable to refresh mailbox watch coverage right now.",
          );
        }
        upsertMailboxConnection(body);
        setMailboxStatus(
          body.watch_status === "active"
            ? "Provider watch coverage is active for this mailbox."
            : body.health_note || "Mailbox watch coverage was refreshed.",
        );
      } catch (mailboxError) {
        setMailboxStatus(
          mailboxError instanceof Error
            ? mailboxError.message
            : "Unable to refresh mailbox watch coverage right now.",
        );
      }
    });
  }

  function toggleMailboxBackgroundSync(connection: CRMMailboxConnection) {
    const nextEnabled = !connection.background_sync_enabled;
    setMailboxStatus(
      nextEnabled
        ? "Turning background sync back on..."
        : "Pausing background sync for this mailbox...",
    );
    startMailboxTransition(async () => {
      try {
        const response = await fetch(
          `/api/crm/inbox/mailboxes/${connection.id}`,
          {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ background_sync_enabled: nextEnabled }),
          },
        );
        const body = (await response.json().catch(() => null)) as
          | CRMMailboxConnection
          | { error?: string }
          | null;
        if (!response.ok || !body || !("id" in body)) {
          throw new Error(
            (body && "error" in body && body.error) ||
              "Unable to update mailbox sync right now.",
          );
        }
        upsertMailboxConnection(body);
        setMailboxStatus(
          nextEnabled
            ? "Background sync is back on for this mailbox."
            : "Background sync is paused for this mailbox.",
        );
      } catch (mailboxError) {
        setMailboxStatus(
          mailboxError instanceof Error
            ? mailboxError.message
            : "Unable to update mailbox sync right now.",
        );
      }
    });
  }

  function disconnectMailbox(connection: CRMMailboxConnection) {
    setMailboxStatus(`Disconnecting ${connection.email_address}...`);
    startMailboxTransition(async () => {
      try {
        const response = await fetch(
          `/api/crm/inbox/mailboxes/${connection.id}`,
          { method: "DELETE" },
        );
        const body = (await response.json().catch(() => null)) as {
          deleted?: boolean;
          error?: string;
        } | null;
        if (!response.ok || !body?.deleted) {
          throw new Error(
            (body && "error" in body && body.error) ||
              "Unable to disconnect the mailbox right now.",
          );
        }
        setMailboxConnections((current) =>
          current.filter((item) => item.id !== connection.id),
        );
        setMailboxStatus(
          `${connection.email_address} was disconnected from Brivoly.`,
        );
      } catch (mailboxError) {
        setMailboxStatus(
          mailboxError instanceof Error
            ? mailboxError.message
            : "Unable to disconnect the mailbox right now.",
        );
      }
    });
  }

  function upsertCalendarConnection(connection: CRMCalendarConnection) {
    setCalendarConnections((current) => {
      const remaining = current.filter((item) => item.id !== connection.id);
      return [connection, ...remaining];
    });
  }

  function connectCalendar() {
    setCalendarStatus("Connecting the calendar to Brivoly...");
    startCalendarTransition(async () => {
      try {
        const response = await fetch("/api/crm/calendars", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            provider: calendarProvider,
            calendar_address: calendarAddress.trim(),
            display_name: calendarDisplayName.trim(),
          }),
        });
        const body = (await response.json().catch(() => null)) as
          | CRMCalendarConnection
          | { error?: string }
          | null;
        if (!response.ok || !body || !("id" in body)) {
          throw new Error(
            (body && "error" in body && body.error) ||
              "Unable to connect the calendar right now.",
          );
        }
        upsertCalendarConnection(body);
        setCalendarStatus(
          `${body.provider === "google_calendar" ? "Google Calendar" : "Outlook Calendar"} is now connected as ${body.calendar_address}.`,
        );
        setCalendarAddress("");
        setCalendarDisplayName("");
      } catch (calendarError) {
        setCalendarStatus(
          calendarError instanceof Error
            ? calendarError.message
            : "Unable to connect the calendar right now.",
        );
      }
    });
  }

  function disconnectCalendar(connection: CRMCalendarConnection) {
    setCalendarStatus(`Disconnecting ${connection.calendar_address}...`);
    startCalendarTransition(async () => {
      try {
        const response = await fetch(`/api/crm/calendars/${connection.id}`, {
          method: "DELETE",
        });
        const body = (await response.json().catch(() => null)) as {
          deleted?: boolean;
          error?: string;
        } | null;
        if (!response.ok || !body?.deleted) {
          throw new Error(
            (body && "error" in body && body.error) ||
              "Unable to disconnect the calendar right now.",
          );
        }
        setCalendarConnections((current) =>
          current.filter((item) => item.id !== connection.id),
        );
        setCalendarStatus(
          `${connection.calendar_address} was disconnected from Brivoly.`,
        );
      } catch (calendarError) {
        setCalendarStatus(
          calendarError instanceof Error
            ? calendarError.message
            : "Unable to disconnect the calendar right now.",
        );
      }
    });
  }

  function toggleCalendarBackgroundSync(connection: CRMCalendarConnection) {
    const nextEnabled = !connection.background_sync_enabled;
    setCalendarStatus(
      nextEnabled
        ? "Turning meeting memory back on..."
        : "Pausing background meeting memory for this calendar...",
    );
    startCalendarTransition(async () => {
      try {
        const response = await fetch(`/api/crm/calendars/${connection.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ background_sync_enabled: nextEnabled }),
        });
        const body = (await response.json().catch(() => null)) as
          | CRMCalendarConnection
          | { error?: string }
          | null;
        if (!response.ok || !body || !("id" in body)) {
          throw new Error(
            (body && "error" in body && body.error) ||
              "Unable to update the calendar right now.",
          );
        }
        upsertCalendarConnection(body);
        setCalendarStatus(
          nextEnabled
            ? "Brivoly can use this calendar for meeting memory again."
            : "Meeting memory is paused for this calendar.",
        );
      } catch (calendarError) {
        setCalendarStatus(
          calendarError instanceof Error
            ? calendarError.message
            : "Unable to update the calendar right now.",
        );
      }
    });
  }

  function ingestCalendarEvent() {
    setCalendarStatus("Bringing this meeting into relationship memory...");
    startCalendarTransition(async () => {
      try {
        const attendeeEmails = calendarAttendeeEmails
          .split(",")
          .map((item) => item.trim().toLowerCase())
          .filter(Boolean);
        const response = await fetch("/api/crm/calendars/events", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            connection_id: calendarConnections[0]?.id ?? null,
            provider: calendarProvider,
            event_id: `calendar-event-${Date.now()}`,
            title: calendarEventTitle.trim(),
            starts_at: calendarEventStartsAt,
            attendee_emails: attendeeEmails,
            notes: calendarEventNotes.trim(),
          }),
        });
        const body = (await response.json().catch(() => null)) as
          | CRMFollowUpOverview
          | { error?: string }
          | null;
        if (!response.ok || !body || !("items" in body)) {
          throw new Error(
            (body && "error" in body && body.error) ||
              "Unable to bring this meeting into Brivoly right now.",
          );
        }
        setOverview(body);
        const matchedLead = attendeeEmails.length
          ? body.items.find((item) =>
              attendeeEmails.includes(item.email_address.trim().toLowerCase()),
            )
          : body.items[0];
        if (matchedLead) {
          setSelectedLeadId(matchedLead.id);
          setSelectedThreadId(
            matchedLead.recent_email_threads[0]?.thread_id ?? null,
          );
        }
        setCalendarStatus(
          "Meeting context saved. Brivoly can now use it in Today and meeting prep.",
        );
        setCalendarEventTitle("");
        setCalendarEventStartsAt("");
        setCalendarAttendeeEmails("");
        setCalendarEventNotes("");
        router.refresh();
      } catch (calendarError) {
        setCalendarStatus(
          calendarError instanceof Error
            ? calendarError.message
            : "Unable to bring this meeting into Brivoly right now.",
        );
      }
    });
  }

  function sendCurrentDraftToMailbox() {
    if (!selectedLead || !emailSubjectDraft.trim() || !emailBodyDraft.trim()) {
      return;
    }
    setEmailStatus("Sending this note through the connected mailbox...");
    startEmailTransition(async () => {
      try {
        const response = await fetch(
          `/api/crm/followups/send/${selectedLead.id}`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              connection_id: preferredMailboxConnection?.id ?? null,
              thread_id: selectedThreadId,
              subject: emailSubjectDraft,
              body: emailBodyDraft,
            }),
          },
        );
        const body = (await response.json().catch(() => null)) as
          | {
              connection: CRMMailboxConnection;
              overview: CRMFollowUpOverview;
              sent_at: string;
              continuity_note: string;
            }
          | { error?: string }
          | null;
        if (!response.ok || !body || !("connection" in body)) {
          throw new Error(
            (body && "error" in body && body.error) ||
              "Unable to send this note right now.",
          );
        }
        setOverview(body.overview);
        upsertMailboxConnection(body.connection);
        setEmailStatus(
          body.continuity_note.trim()
            ? `${body.continuity_note} Sent through ${body.connection.provider === "gmail" ? "Gmail" : "Outlook"} at ${body.connection.email_address}.`
            : `Sent through ${body.connection.provider === "gmail" ? "Gmail" : "Outlook"} at ${body.connection.email_address}${selectedThread ? ` and kept attached to ${selectedThread.subject}.` : "."}`,
        );
        router.refresh();
      } catch (sendError) {
        setEmailStatus(
          sendError instanceof Error
            ? sendError.message
            : "Unable to send this note right now.",
        );
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
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
                Bring context back in
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">
                Bring relationship context in without retyping it.
              </h2>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                Upload a CSV, XLSX, XLS, or note image, or paste a Google Sheets
                link. Brivoly makes sense of the rough edges, spots what is
                missing, and keeps only what is ready to support the next touch.
              </p>

              <div className="mt-5 flex flex-wrap gap-3">
                <Button
                  variant={sourceType === "file_upload" ? "default" : "outline"}
                  onClick={() => resetImportWorkspace("file_upload")}
                >
                  Spreadsheet or file
                </Button>
                <Button
                  variant={
                    sourceType === "google_sheets" ? "default" : "outline"
                  }
                  onClick={() => resetImportWorkspace("google_sheets")}
                >
                  Sheet link
                </Button>
                {hasImportWorkspaceState ? (
                  <Button
                    variant="outline"
                    onClick={() => resetImportWorkspace(sourceType)}
                  >
                    Start over
                  </Button>
                ) : null}
              </div>

              {sourceType === "file_upload" ? (
                <section className="mt-5 rounded-[1.4rem] border bg-slate-50/80 p-5">
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
                    File or note
                  </p>
                  <input
                    ref={fileInputRef}
                    type="file"
                    data-testid="crm-import-file-input"
                    accept=".csv,text/csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,.xls,application/vnd.ms-excel,.png,image/png,.jpg,image/jpeg,.jpeg,image/jpeg,.webp,image/webp"
                    className="mt-3 block w-full rounded-2xl border border-dashed border-slate-300 bg-white px-4 py-5 text-sm text-slate-600"
                    onChange={(event) => {
                      resetImportWorkspace("file_upload");
                      setSelectedFile(event.target.files?.[0] ?? null);
                    }}
                  />
                  <p className="mt-3 text-xs text-slate-500">
                    Supported: CSV, XLSX, XLS, PNG, JPG, JPEG, and WEBP. Helpful
                    columns include contact, company, owner, next touch, and
                    notes you would want back in memory.
                  </p>
                  {selectedFile ? (
                    <p className="mt-2 text-sm font-medium text-slate-700">
                      {selectedFile.name}
                    </p>
                  ) : null}
                  {selectedFile && isImageFile(selectedFile.name) ? (
                    <p className="mt-2 text-xs text-slate-500">
                      Brivoly will use your saved AI reading defaults to turn
                      this note image into relationship-ready rows.
                    </p>
                  ) : null}
                </section>
              ) : (
                <section className="mt-5 rounded-[1.4rem] border bg-slate-50/80 p-5">
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
                    Sheet link
                  </p>
                  <input
                    value={sheetUrl}
                    onChange={(event) => {
                      resetImportWorkspace("google_sheets");
                      setSheetUrl(event.target.value);
                    }}
                    placeholder="https://docs.google.com/spreadsheets/d/..."
                    className="mt-3 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400"
                  />
                  <p className="mt-3 text-xs text-slate-500">
                    Use a shareable Google Sheets URL. Brivoly will pull the
                    context in directly and keep only what is worth carrying
                    forward.
                  </p>
                </section>
              )}

              <div className="mt-5 flex flex-wrap gap-3">
                <Button
                  disabled={isImportPending}
                  onClick={() => requestImportPreview()}
                >
                  {isImportPending
                    ? "Checking..."
                    : importPreview
                      ? "Re-check context"
                      : "Check context"}
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

              {importError ? (
                <p className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  {importError}
                </p>
              ) : null}
              {importStatus ? (
                <p className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
                  {importStatus}
                </p>
              ) : null}
              {isImportMappingDirty ? (
                <p className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                  Column mappings changed. Re-check the preview so Brivoly can
                  validate the updated layout before bringing this in.
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
            ambientMemorySummary={overview.ambient_memory_summary}
            onOpenAmbientMemoryAction={openAmbientMemoryAction}
          />
        </div>
      ) : null}

      {showingFollowups ? (
        <section className="mt-6 grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
          <section className="rounded-[1.75rem] border bg-white/80 p-6 shadow-sm">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
              Relationship memory
            </p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">
              Keep context close to the next touch.
            </h2>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              Search fast, spot quiet relationships, and move the next touch
              forward without losing the last meaningful interaction.
            </p>
            {error ? (
              <p className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                {error}
              </p>
            ) : null}
            <div className="mt-5 rounded-[1.4rem] border bg-slate-50/80 p-4">
              <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
                <div className="flex flex-col gap-3 sm:flex-row">
                  <input
                    value={relationshipQuery}
                    onChange={(event) => setRelationshipQuery(event.target.value)}
                    placeholder="Search client, company, notes, open loop, upload context, or next step"
                    className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400"
                  />
                  {(relationshipQuery || relationshipFilter !== "all") && (
                    <button
                      type="button"
                      onClick={() => {
                        setRelationshipQuery("");
                        setRelationshipFilter("all");
                      }}
                      className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-700 transition hover:border-slate-400 hover:text-slate-950"
                    >
                      Clear view
                    </button>
                  )}
                </div>
                <div className="flex flex-wrap gap-2">
                  {[
                    { value: "all", label: "All" },
                    { value: "due", label: "Today" },
                    { value: "reply", label: "Reply soon" },
                    { value: "fresh_context", label: "Fresh context" },
                    { value: "open_loop", label: "Open loop" },
                    { value: "stale", label: "Reconnect" },
                    { value: "at_risk", label: "At risk" },
                  ].map((item) => (
                    <button
                      key={item.value}
                      type="button"
                      onClick={() =>
                        setRelationshipFilter(item.value as RelationshipFilter)
                      }
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
            {filteredFollowUps[0] ? (
              <div className="mt-5 rounded-[1.4rem] border border-slate-900 bg-slate-950 px-5 py-5 text-white shadow-sm">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="max-w-2xl">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-200">
                      Start with this relationship
                    </p>
                    <p className="mt-2 text-2xl font-semibold tracking-tight">
                      {filteredFollowUps[0].lead_name}
                    </p>
                    <p className="mt-1 text-sm text-slate-300">
                      {filteredFollowUps[0].company_name}
                    </p>
                    <p className="mt-3 text-sm leading-6 text-slate-200">
                      {getLeadCardWhyNow(filteredFollowUps[0])}
                    </p>
                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                      <TimelineTileDark
                        label="Latest saved moment"
                        value={getLeadCardStory(filteredFollowUps[0])}
                      />
                      <TimelineTileDark
                        label="Best next touch"
                        value={
                          isReconnectMoment(filteredFollowUps[0])
                            ? filteredFollowUps[0].relationship_reconnect_next_move ||
                              filteredFollowUps[0].next_step
                            : getNewestThread(filteredFollowUps[0])?.open_loop ||
                              getNewestThread(filteredFollowUps[0])?.next_touch_hint ||
                              filteredFollowUps[0].next_step
                        }
                      />
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2 lg:justify-end">
                    <Button
                      type="button"
                      onClick={() => setSelectedLeadId(filteredFollowUps[0].id)}
                      className="border border-white/20 bg-white text-slate-950 hover:bg-slate-100"
                    >
                      Open relationship
                    </Button>
                    {filteredFollowUps[0].recent_email_threads.some(
                      (thread) => thread.needs_reply,
                    ) ? (
                      <Button
                        type="button"
                        variant="outline"
                        className="border-white/20 bg-transparent text-white hover:bg-white/10 hover:text-white"
                        onClick={() =>
                          runTodayPriorityAction(
                            filteredFollowUps[0].id,
                            "/clientos/follow-ups",
                            {
                              objective: "follow_up",
                              tone: "warm",
                              length: "short",
                              status:
                                "Drafting a reply from relationship memory...",
                            },
                            undefined,
                            getReplyThread(filteredFollowUps[0])?.thread_id ??
                              null,
                          )
                        }
                      >
                        Draft reply
                      </Button>
                    ) : isReconnectMoment(filteredFollowUps[0]) ? (
                      <Button
                        type="button"
                        variant="outline"
                        className="border-white/20 bg-transparent text-white hover:bg-white/10 hover:text-white"
                        onClick={() =>
                          runTodayPriorityAction(
                            filteredFollowUps[0].id,
                            "/clientos/follow-ups",
                            {
                              objective: "revive",
                              tone: "warm",
                              length: "short",
                              status:
                                "Drafting a reconnect from relationship memory...",
                            },
                          )
                        }
                      >
                        Draft reconnect
                      </Button>
                    ) : null}
                  </div>
                </div>
              </div>
            ) : null}
            {filteredFollowUps.length > 1 ? (
              <div className="mt-5 rounded-[1.35rem] border bg-slate-50/80 px-5 py-4">
                <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                      After that
                    </p>
                    <p className="mt-2 text-sm leading-6 text-slate-600">
                      Once the first relationship is handled, these are the next
                      touches Brivoly would keep close without turning the page
                      into a wall of equal-weight cards.
                    </p>
                  </div>
                  <p className="text-xs text-slate-500">
                    Let the rest stay quiet until you need them.
                  </p>
                </div>
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  {filteredFollowUps.slice(1, 3).map((item) => (
                    <div
                      key={`${item.id}-memory-next`}
                      className="rounded-[1rem] border bg-white px-4 py-4"
                    >
                      <p className="text-sm font-medium text-slate-900">
                        {item.lead_name}
                      </p>
                      <p className="mt-1 text-xs text-slate-500">
                        {item.company_name}
                      </p>
                      <p className="mt-3 text-sm leading-6 text-slate-600">
                        {getLeadCardWhyNow(item)}
                      </p>
                      <p className="mt-3 text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                        Best next touch
                      </p>
                      <p className="mt-2 text-sm leading-6 text-slate-700">
                        {isReconnectMoment(item)
                          ? item.relationship_reconnect_next_move ||
                            item.next_step
                          : getNewestThread(item)?.open_loop ||
                            getNewestThread(item)?.next_touch_hint ||
                            item.next_step}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            {filteredFollowUps.length > 3 ? (
              <div className="mt-5 rounded-[1.35rem] border bg-white px-5 py-4">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                  Can wait quietly
                </p>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  These relationships are still in view, but they do not need
                  the same urgency as the first few.
                </p>
                <div className="mt-4 flex flex-wrap gap-2">
                  {filteredFollowUps.slice(3, 8).map((item) => (
                    <button
                      key={`${item.id}-quiet-pill`}
                      type="button"
                      onClick={() => setSelectedLeadId(item.id)}
                      className="rounded-full border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-700 transition hover:border-slate-400 hover:bg-white hover:text-slate-950"
                    >
                      {item.lead_name}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
            <div className="mt-6 space-y-4">
              {filteredFollowUps.map((item) => {
                const rowPending = pendingId === item.id && isPending;
                const selected = item.id === selectedLead?.id;
                return (
                  <article
                    key={item.id}
                    className={`rounded-[1.5rem] border p-5 transition ${selected ? "border-slate-900 bg-white shadow-sm" : "bg-slate-50/80"}`}
                  >
                    <button
                      type="button"
                      className="w-full text-left"
                      onClick={() => setSelectedLeadId(item.id)}
                    >
                      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">
                            {formatRelationshipState(item.relationship_state)} ·{" "}
                            {item.contact_channel}
                          </p>
                          <h3 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                            {item.lead_name}
                          </h3>
                          <p className="mt-1 text-sm text-slate-600">
                            {item.company_name}
                          </p>
                          <p className="mt-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                            Owner · {item.owner_name}
                          </p>
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                          {item.recent_email_threads.some(
                            (thread) => thread.needs_reply,
                          ) ? (
                            <MiniFlag tone="critical" label="Reply soon" />
                          ) : null}
                          {hasRecentUploadContext(item) ? (
                            <MiniFlag tone="neutral" label="Fresh context" />
                          ) : null}
                          {item.relationship_state === "stale" ? (
                            <MiniFlag tone="warning" label="Stale" />
                          ) : null}
                          {item.relationship_state === "drifting" ? (
                            <MiniFlag tone="warning" label="Drifting" />
                          ) : null}
                          {item.relationship_state === "at_risk" ? (
                            <MiniFlag tone="critical" label="At risk" />
                          ) : null}
                          <PriorityBadge priority={item.priority} />
                        </div>
                      </div>
                      <p className="mt-4 text-sm font-medium text-slate-700">
                        Next touch
                      </p>
                      <p className="mt-1 text-sm leading-6 text-slate-600">
                        {item.next_step}
                      </p>
                      <div className="mt-4 grid gap-3 md:grid-cols-2">
                        <TimelineTile
                          label="Latest saved moment"
                          value={getLeadCardStory(item)}
                        />
                        <TimelineTile
                          label="Open loop"
                          value={
                            getNewestThread(item)?.open_loop ||
                            getNewestThread(item)?.unresolved_hint ||
                            item.relationship_reconnect_next_move ||
                            item.next_step
                          }
                        />
                      </div>
                      <div className="mt-5 grid gap-3 md:grid-cols-2">
                        <TimelineTile
                          label="Why now"
                          value={getLeadCardWhyNow(item)}
                        />
                        <TimelineTile
                          label="Next timing"
                          value={formatDateTime(item.next_follow_up_at)}
                        />
                      </div>
                    </button>
                    <div className="mt-5 flex flex-wrap gap-3">
                      {item.recent_email_threads.some(
                        (thread) => thread.needs_reply,
                      ) ? (
                        <Button
                          variant="outline"
                          onClick={() =>
                            runTodayPriorityAction(
                              item.id,
                              "/clientos/follow-ups",
                              {
                                objective: "follow_up",
                                tone: "warm",
                                length: "short",
                                status:
                                  "Drafting a reply from relationship memory...",
                              },
                              undefined,
                              getReplyThread(item)?.thread_id ?? null,
                            )
                          }
                        >
                          Draft reply
                        </Button>
                      ) : null}
                      {isReconnectMoment(item) ? (
                        <Button
                          variant="outline"
                          onClick={() =>
                            runTodayPriorityAction(
                              item.id,
                              "/clientos/follow-ups",
                              {
                                objective: "revive",
                                tone: "warm",
                                length: "short",
                                status:
                                  "Drafting a reconnect from relationship memory...",
                              },
                            )
                          }
                        >
                          Draft reconnect
                        </Button>
                      ) : null}
                      {hasOpenLoop(item) &&
                      !item.recent_email_threads.some(
                        (thread) => thread.needs_reply,
                      ) ? (
                        <Button
                          variant="outline"
                          onClick={() =>
                            runTodayPriorityAction(
                              item.id,
                              "/clientos/follow-ups",
                              {
                                objective: "close_loop",
                                tone: "direct",
                                length: "short",
                                status:
                                  "Drafting a close-the-loop note from relationship memory...",
                              },
                              undefined,
                              getReplyThread(item)?.thread_id ??
                                getNewestThread(item)?.thread_id ??
                                null,
                            )
                          }
                        >
                          Close loop
                        </Button>
                      ) : null}
                      {hasRecentUploadContext(item) ? (
                        <Button
                          variant="outline"
                          onClick={() => setSelectedLeadId(item.id)}
                        >
                          Review context
                        </Button>
                      ) : null}
                      <Button
                        disabled={rowPending}
                        onClick={() =>
                          runAction(item.id, { action: "complete" })
                        }
                      >
                        {rowPending ? "Updating..." : "Done"}
                      </Button>
                      <Button
                        variant="outline"
                        disabled={rowPending}
                        onClick={() =>
                          runAction(item.id, {
                            action: "snooze",
                            snooze_hours: 24,
                          })
                        }
                      >
                        Tomorrow
                      </Button>
                      <Button
                        variant="outline"
                        disabled={rowPending}
                        onClick={() =>
                          runAction(item.id, {
                            action: "snooze",
                            snooze_hours: 72,
                          })
                        }
                      >
                        Later this week
                      </Button>
                    </div>
                  </article>
                );
              })}
              {!filteredFollowUps.length ? (
                <div className="rounded-[1.5rem] border border-dashed bg-slate-50/70 p-6 text-sm leading-6 text-slate-600">
                  <p>
                    No relationships match this view yet. Try a different
                    keyword or filter.
                  </p>
                  {(relationshipQuery || relationshipFilter !== "all") && (
                    <div className="mt-4">
                      <button
                        type="button"
                        onClick={() => {
                          setRelationshipQuery("");
                          setRelationshipFilter("all");
                        }}
                        className="rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-700 transition hover:border-slate-400 hover:text-slate-950"
                      >
                        Reset relationship view
                      </button>
                    </div>
                  )}
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
                canSendFromMailbox={mailboxConnections.length > 0}
                selectedThread={selectedThread}
                preferredMailboxConnection={preferredMailboxConnection}
                draftFocusToken={draftFocusToken}
                onEmailObjectiveChange={setEmailObjective}
                onEmailToneChange={setEmailTone}
                onEmailLengthChange={setEmailLength}
                onEmailSubjectDraftChange={setEmailSubjectDraft}
                onEmailBodyDraftChange={setEmailBodyDraft}
                onGenerateEmailDraft={generateEmailDraft}
                onSendDraftToMailbox={sendCurrentDraftToMailbox}
                initialMemoryView={requestedMemoryView}
              />
            ) : null}
            <section className="rounded-[1.75rem] border bg-slate-950 p-6 text-slate-50 shadow-[0_24px_90px_-55px_rgba(15,23,42,0.9)]">
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-300">
                Why Brivoly feels lighter
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight">
                Brivoly remembers relationships so freelancers do not have to.
              </h2>
              <ul className="mt-5 space-y-3 text-sm leading-6 text-slate-300">
                <li>
                  Every note, reminder, and suggested message should lower
                  mental overhead instead of adding admin.
                </li>
                <li>
                  Brivoly should help you stay warm, responsive, and top-of-mind
                  without more software work.
                </li>
                <li>
                  The goal is continuity and follow-through, not status
                  management.
                </li>
              </ul>
            </section>
          </section>
        </section>
      ) : null}

      {showingInbox ? (
        <section className="mt-6 grid gap-6 xl:grid-cols-[0.92fr_1.08fr]">
          <section className="rounded-[1.75rem] border bg-white/85 p-6 shadow-sm">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
              Inbox memory
            </p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">
              Let Brivoly keep relationship context current from email.
            </h2>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              Brivoly turns email activity into living relationship memory: it
              matches contacts by email, creates missing contacts automatically,
              and keeps the right conversation attached to the right person.
            </p>
            {connectionFocus &&
            overview.ambient_memory_summary?.suggested_action_note ? (
              <div className="mt-4 rounded-[1.2rem] border border-slate-200 bg-slate-50/80 px-4 py-4">
                <p className="text-sm leading-6 text-slate-700">
                  {overview.ambient_memory_summary.suggested_action_note}
                </p>
              </div>
            ) : null}

            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <CompactMetricLight
                label="Reply soon"
                value={String(overview.inbox_summary?.needs_reply_count ?? 0)}
                tone="critical"
              />
              <CompactMetricLight
                label="Waiting on them"
                value={String(
                  overview.inbox_summary?.waiting_on_contact_count ?? 0,
                )}
                tone="warning"
              />
              <CompactMetricLight
                label="Quiet threads"
                value={String(overview.inbox_summary?.stale_thread_count ?? 0)}
                tone="neutral"
              />
            </div>

            <section
              ref={mailboxSectionRef}
              className={`mt-6 rounded-[1.4rem] border bg-slate-50/80 p-5 ${
                connectionFocus === "mailbox" || connectionFocus === "all"
                  ? "border-slate-400 bg-white/95 shadow-[0_18px_60px_-40px_rgba(15,23,42,0.35)]"
                  : ""
              }`}
            >
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                Connected mailboxes
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                Connect Gmail or Outlook once, then let Brivoly pull thread
                context back into relationship memory and send notes from the
                same account.
              </p>
              <div className="mt-4 grid gap-3 md:grid-cols-4">
                <CompactMetricLight
                  label="Event-ready inboxes"
                  value={`${mailboxConnections.filter((connection) => connection.event_ready).length} inbox${mailboxConnections.filter((connection) => connection.event_ready).length === 1 ? "" : "es"}`}
                  tone={
                    mailboxConnections.some((connection) => connection.event_ready)
                      ? "positive"
                      : "neutral"
                  }
                />
                <CompactMetricLight
                  label="Quiet inboxes"
                  value={`${mailboxConnections.filter((connection) => isMailboxQuiet(connection)).length} inbox${mailboxConnections.filter((connection) => isMailboxQuiet(connection)).length === 1 ? "" : "es"}`}
                  tone={
                    mailboxConnections.some((connection) => isMailboxQuiet(connection))
                      ? "warning"
                      : "neutral"
                  }
                />
                <CompactMetricLight
                  label="Reconnect needed"
                  value={`${mailboxConnections.filter((connection) => mailboxNeedsReconnect(connection)).length} inbox${mailboxConnections.filter((connection) => mailboxNeedsReconnect(connection)).length === 1 ? "" : "es"}`}
                  tone={
                    mailboxConnections.some(
                      (connection) => mailboxNeedsReconnect(connection),
                    )
                      ? "critical"
                      : "neutral"
                  }
                />
                <CompactMetricLight
                  label="Paused inbox memory"
                  value={`${mailboxConnections.filter((connection) => !connection.background_sync_enabled).length} inbox${mailboxConnections.filter((connection) => !connection.background_sync_enabled).length === 1 ? "" : "es"}`}
                  tone={
                    mailboxConnections.some(
                      (connection) => !connection.background_sync_enabled,
                    )
                      ? "warning"
                      : "neutral"
                  }
                />
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <button
                  type="button"
                  disabled={isMailboxPending}
                  onClick={() => startMailboxOAuth("gmail")}
                  className={`rounded-[1.2rem] border bg-white px-4 py-4 text-left transition hover:border-slate-400 disabled:cursor-not-allowed disabled:opacity-70 ${
                    ambientActionKind === "connect" &&
                    (connectionFocus === "mailbox" || connectionFocus === "all")
                      ? "border-slate-400 bg-slate-50"
                      : ""
                  }`}
                >
                  <p className="ui-eyebrow">Gmail</p>
                  <p className="mt-2 text-base font-semibold text-slate-950">
                    Connect the real Gmail account
                  </p>
                  <p className="mt-2 text-sm leading-6 text-slate-600">
                    Use Google consent, keep the inbox in sync, and send notes
                    through the same mailbox.
                  </p>
                </button>
                <button
                  type="button"
                  disabled={isMailboxPending}
                  onClick={() => startMailboxOAuth("outlook")}
                  className={`rounded-[1.2rem] border bg-white px-4 py-4 text-left transition hover:border-slate-400 disabled:cursor-not-allowed disabled:opacity-70 ${
                    ambientActionKind === "connect" &&
                    (connectionFocus === "mailbox" || connectionFocus === "all")
                      ? "border-slate-400 bg-slate-50"
                      : ""
                  }`}
                >
                  <p className="ui-eyebrow">Outlook</p>
                  <p className="mt-2 text-base font-semibold text-slate-950">
                    Connect the real Outlook account
                  </p>
                  <p className="mt-2 text-sm leading-6 text-slate-600">
                    Use Microsoft consent, keep the inbox in sync, and send
                    notes through the same mailbox.
                  </p>
                </button>
              </div>
              <div className="mt-5 rounded-[1.2rem] border border-dashed bg-white px-4 py-4">
                <p className="ui-eyebrow">Fallback path</p>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  If provider credentials are not configured yet, you can still
                  add a manual mailbox connection below and keep using sync
                  preview mode.
                </p>
                <div className="mt-4 grid gap-3 xl:grid-cols-[0.8fr_1.2fr_1fr_auto]">
                  <label className="block">
                    <span className="ui-eyebrow">Provider</span>
                    <select
                      value={mailboxProvider}
                      onChange={(event) =>
                        setMailboxProvider(
                          event.target.value as "gmail" | "outlook",
                        )
                      }
                      className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400"
                    >
                      <option value="gmail">Gmail</option>
                      <option value="outlook">Outlook</option>
                    </select>
                  </label>
                  <label className="block">
                    <span className="ui-eyebrow">Mailbox email</span>
                    <input
                      value={mailboxEmail}
                      onChange={(event) => setMailboxEmail(event.target.value)}
                      placeholder="you@yourstudio.com"
                      className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400"
                    />
                  </label>
                  <label className="block">
                    <span className="ui-eyebrow">Name on the mailbox</span>
                    <input
                      value={mailboxDisplayName}
                      onChange={(event) =>
                        setMailboxDisplayName(event.target.value)
                      }
                      placeholder="Ada from Northstar"
                      className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400"
                    />
                  </label>
                  <div className="flex items-end">
                    <Button
                      disabled={isMailboxPending}
                      onClick={connectMailbox}
                      className={
                        ambientActionKind === "connect" &&
                        (connectionFocus === "mailbox" ||
                          connectionFocus === "all")
                          ? emphasizedActionClass
                          : undefined
                      }
                    >
                      {isMailboxPending
                        ? "Connecting..."
                        : "Add manual connection"}
                    </Button>
                  </div>
                </div>
              </div>
              <div className="mt-4 space-y-3">
                {mailboxConnections.length ? (
                  mailboxConnections.map((connection) => (
                    <div
                      key={connection.id}
                      className="rounded-[1.2rem] border bg-white px-4 py-4"
                    >
                      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                        <div>
                          <p className="text-sm font-semibold text-slate-950">
                            {connection.provider === "gmail"
                              ? "Gmail"
                              : "Outlook"}{" "}
                            · {connection.email_address}
                          </p>
                          <p className="mt-1 text-sm text-slate-600">
                            {connection.display_name || "Mailbox account"} ·{" "}
                            {connection.connection_mode === "oauth"
                              ? "provider-linked"
                              : "manual beta"}{" "}
                            ·{" "}
                            {connection.last_sync_at
                              ? `last synced ${formatDateTime(connection.last_sync_at)}`
                              : "not synced yet"}
                          </p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <MiniFlag
                            label={`${connection.sent_message_count} sent`}
                            tone="neutral"
                          />
                          <MiniFlag
                            label={`${connection.last_synced_thread_count} synced`}
                            tone="warning"
                          />
                          <MiniFlag
                            label={
                              connection.background_sync_enabled
                                ? "background sync on"
                                : "background sync paused"
                            }
                            tone={
                              connection.background_sync_enabled
                                ? "neutral"
                                : "warning"
                            }
                          />
                          <MiniFlag
                            label={`${connection.watch_event_count} watch event${connection.watch_event_count === 1 ? "" : "s"}`}
                            tone="neutral"
                          />
                          <MiniFlag
                            label={`watch ${connection.watch_status || "inactive"}`}
                            tone={
                              connection.watch_status === "active"
                                ? "neutral"
                                : connection.watch_status === "manual"
                                  ? "warning"
                                  : "warning"
                            }
                          />
                          {connection.sync_stale ? (
                            <MiniFlag label="sync stale" tone="warning" />
                          ) : null}
                          {isMailboxTokenExpiringSoon(connection) ? (
                            <MiniFlag label="token soon" tone="warning" />
                          ) : null}
                          {connection.reauth_required ? (
                            <MiniFlag label="reauth needed" tone="warning" />
                          ) : null}
                          {connection.connection_mode === "oauth" &&
                          (connection.reauth_required ||
                            connection.status === "needs_reauth") ? (
                            <Button
                              type="button"
                              variant="outline"
                              disabled={isMailboxPending}
                              onClick={() =>
                                startMailboxOAuth(
                                  connection.provider === "gmail"
                                    ? "gmail"
                                    : "outlook",
                                )
                              }
                              className={
                                ambientActionKind === "reconnect" &&
                                (connectionFocus === "mailbox" ||
                                  connectionFocus === "all")
                                  ? emphasizedActionClass
                                  : undefined
                              }
                            >
                              Reconnect
                            </Button>
                          ) : null}
                          <Button
                            type="button"
                            variant="outline"
                            disabled={isMailboxPending}
                            onClick={() =>
                              toggleMailboxBackgroundSync(connection)
                            }
                            className={
                              ambientActionKind === "resume" &&
                              !connection.background_sync_enabled &&
                              (connectionFocus === "mailbox" ||
                                connectionFocus === "all")
                                ? emphasizedActionClass
                                : undefined
                            }
                          >
                            {connection.background_sync_enabled
                              ? "Pause sync"
                              : "Resume sync"}
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            disabled={
                              isMailboxPending ||
                              connection.connection_mode !== "oauth" ||
                              connection.reauth_required
                            }
                            onClick={() => renewMailboxWatch(connection)}
                          >
                            {isMailboxPending
                              ? "Refreshing..."
                              : "Refresh watch"}
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            disabled={
                              isMailboxPending || connection.reauth_required
                            }
                            onClick={() => syncMailboxConnection(connection.id)}
                            className={
                              ambientActionKind === "sync" &&
                              connection.background_sync_enabled &&
                              !connection.reauth_required &&
                              (connectionFocus === "mailbox" ||
                                connectionFocus === "all")
                                ? emphasizedActionClass
                                : undefined
                            }
                          >
                            {isMailboxPending ? "Syncing..." : "Sync now"}
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            disabled={isMailboxPending}
                            onClick={() => disconnectMailbox(connection)}
                          >
                            Disconnect
                          </Button>
                        </div>
                      </div>
                      {connection.last_watch_event_at ? (
                        <p className="mt-3 text-xs text-slate-500">
                          Last watch-triggered sync{" "}
                          {formatDateTime(connection.last_watch_event_at)}.
                        </p>
                      ) : null}
                      <div className="mt-4 grid gap-3 md:grid-cols-2">
                        <TimelineTile
                          label="What Brivoly sees"
                          value={
                            connection.continuity_summary ||
                            getMailboxConnectionStateDetail(connection)
                          }
                        />
                        <TimelineTile
                          label="Smallest useful fix"
                          value={getMailboxConnectionFix(connection)}
                        />
                        <TimelineTile
                          label="Watch coverage"
                          value={getMailboxWatchRead(connection)}
                        />
                        <TimelineTile
                          label="Continuity state"
                          value={getMailboxConnectionStateLabel(connection)}
                        />
                      </div>
                      {connection.watch_expires_at ? (
                        <p className="mt-2 text-xs text-slate-500">
                          Watch coverage renews by{" "}
                          {formatDateTime(connection.watch_expires_at)}.
                        </p>
                      ) : null}
                      {connection.continuity_summary ? (
                        <p className="mt-2 text-xs text-slate-500">
                          {connection.continuity_summary}
                        </p>
                      ) : null}
                      {connection.last_sent_at ? (
                        <p className="mt-2 text-xs text-slate-500">
                          Last provider-backed note sent{" "}
                          {formatDateTime(connection.last_sent_at)}.
                        </p>
                      ) : null}
                      {connection.health_note ? (
                        <p className="mt-2 text-xs text-amber-700">
                          {connection.health_note}
                        </p>
                      ) : null}
                    </div>
                  ))
                ) : (
                  <div className="rounded-[1.2rem] border border-dashed bg-white px-4 py-4 text-sm leading-6 text-slate-600">
                    No mailbox is connected yet. Add Gmail or Outlook above so
                    Brivoly can start syncing conversation context instead of
                    relying on manual thread previews.
                  </div>
                )}
              </div>
              {mailboxStatus ? (
                <p className="mt-4 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700">
                  {mailboxStatus}
                </p>
              ) : null}
            </section>

            <section
              ref={calendarSectionRef}
              className={`mt-6 rounded-[1.4rem] border bg-slate-50/80 p-5 ${
                connectionFocus === "calendar" || connectionFocus === "all"
                  ? "border-slate-400 bg-white/95 shadow-[0_18px_60px_-40px_rgba(15,23,42,0.35)]"
                  : ""
              }`}
            >
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                Connected calendars
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                Calendar beta: connect the address you usually schedule from,
                then bring meetings into relationship memory so Brivoly can prep
                the next conversation before it starts.
              </p>
              <div className="mt-4 grid gap-3 md:grid-cols-4">
                <CompactMetricLight
                  label="Warm calendars"
                  value={`${calendarConnections.filter((connection) => connection.memory_warm).length} calendar${calendarConnections.filter((connection) => connection.memory_warm).length === 1 ? "" : "s"}`}
                  tone={
                    calendarConnections.some((connection) => connection.memory_warm)
                      ? "positive"
                      : "neutral"
                  }
                />
                <CompactMetricLight
                  label="Quiet calendars"
                  value={`${calendarConnections.filter((connection) => isCalendarQuiet(connection)).length} calendar${calendarConnections.filter((connection) => isCalendarQuiet(connection)).length === 1 ? "" : "s"}`}
                  tone={
                    calendarConnections.some((connection) => isCalendarQuiet(connection))
                      ? "warning"
                      : "neutral"
                  }
                />
                <CompactMetricLight
                  label="Needs care"
                  value={`${calendarConnections.filter((connection) => calendarNeedsAttention(connection)).length} calendar${calendarConnections.filter((connection) => calendarNeedsAttention(connection)).length === 1 ? "" : "s"}`}
                  tone={
                    calendarConnections.some((connection) =>
                      calendarNeedsAttention(connection),
                    )
                      ? "critical"
                      : "neutral"
                  }
                />
                <CompactMetricLight
                  label="Paused meeting memory"
                  value={`${calendarConnections.filter((connection) => !connection.background_sync_enabled).length} calendar${calendarConnections.filter((connection) => !connection.background_sync_enabled).length === 1 ? "" : "s"}`}
                  tone={
                    calendarConnections.some(
                      (connection) => !connection.background_sync_enabled,
                    )
                      ? "warning"
                      : "neutral"
                  }
                />
              </div>
              <div className="mt-4 rounded-[1.2rem] border border-dashed bg-white px-4 py-4">
                <p className="ui-eyebrow">Calendar connection</p>
                <div className="mt-4 grid gap-3 xl:grid-cols-[0.8fr_1.2fr_1fr_auto]">
                  <label className="block">
                    <span className="ui-eyebrow">Provider</span>
                    <select
                      value={calendarProvider}
                      onChange={(event) =>
                        setCalendarProvider(
                          event.target.value as
                            | "google_calendar"
                            | "outlook_calendar",
                        )
                      }
                      className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400"
                    >
                      <option value="google_calendar">Google Calendar</option>
                      <option value="outlook_calendar">Outlook Calendar</option>
                    </select>
                  </label>
                  <label className="block">
                    <span className="ui-eyebrow">Calendar address</span>
                    <input
                      value={calendarAddress}
                      onChange={(event) =>
                        setCalendarAddress(event.target.value)
                      }
                      placeholder="you@yourstudio.com"
                      className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400"
                    />
                  </label>
                  <label className="block">
                    <span className="ui-eyebrow">Name on the calendar</span>
                    <input
                      value={calendarDisplayName}
                      onChange={(event) =>
                        setCalendarDisplayName(event.target.value)
                      }
                      placeholder="Northstar schedule"
                      className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400"
                    />
                  </label>
                  <div className="flex items-end">
                    <Button
                      disabled={isCalendarPending}
                      onClick={connectCalendar}
                      className={
                        ambientActionKind === "connect" &&
                        (connectionFocus === "calendar" ||
                          connectionFocus === "all")
                          ? emphasizedActionClass
                          : undefined
                      }
                    >
                      {isCalendarPending ? "Connecting..." : "Add calendar"}
                    </Button>
                  </div>
                </div>
              </div>
              <div className="mt-4 space-y-3">
                {calendarConnections.length ? (
                  calendarConnections.map((connection) => (
                    <div
                      key={connection.id}
                      className="rounded-[1.2rem] border bg-white px-4 py-4"
                    >
                      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                        <div>
                          <p className="text-sm font-semibold text-slate-950">
                            {connection.provider === "google_calendar"
                              ? "Google Calendar"
                              : "Outlook Calendar"}{" "}
                            · {connection.calendar_address}
                          </p>
                          <p className="mt-1 text-sm text-slate-600">
                            {connection.display_name || "Calendar account"} ·{" "}
                            {connection.last_sync_at
                              ? `last event saved ${formatDateTime(connection.last_sync_at)}`
                              : "no meeting context saved yet"}
                          </p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <MiniFlag
                            label={
                              connection.background_sync_enabled
                                ? "memory on"
                                : "memory paused"
                            }
                            tone={
                              connection.background_sync_enabled
                                ? "neutral"
                                : "warning"
                            }
                          />
                          {connection.memory_warm ? (
                            <MiniFlag label="context warm" tone="neutral" />
                          ) : null}
                          {connection.sync_stale ? (
                            <MiniFlag label="context quiet" tone="warning" />
                          ) : null}
                          <Button
                            type="button"
                            variant="outline"
                            disabled={isCalendarPending}
                            onClick={() =>
                              toggleCalendarBackgroundSync(connection)
                            }
                            className={
                              ambientActionKind === "resume" &&
                              !connection.background_sync_enabled &&
                              (connectionFocus === "calendar" ||
                                connectionFocus === "all")
                                ? emphasizedActionClass
                                : undefined
                            }
                          >
                            {connection.background_sync_enabled
                              ? "Pause memory"
                              : "Resume memory"}
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            disabled={isCalendarPending}
                            onClick={() => disconnectCalendar(connection)}
                          >
                            Disconnect
                          </Button>
                        </div>
                      </div>
                      {connection.last_sync_at ? (
                        <p className="mt-2 text-xs text-slate-500">
                          Last meeting context saved{" "}
                          {formatDateTime(connection.last_sync_at)}.
                        </p>
                      ) : null}
                      <div className="mt-4 grid gap-3 md:grid-cols-2">
                        <TimelineTile
                          label="What Brivoly sees"
                          value={
                            connection.continuity_summary ||
                            getCalendarConnectionStateDetail(connection)
                          }
                        />
                        <TimelineTile
                          label="Smallest useful fix"
                          value={getCalendarConnectionFix(connection)}
                        />
                        <TimelineTile
                          label="Latest prep signal"
                          value={getCalendarWarmthRead(connection)}
                        />
                        <TimelineTile
                          label="Continuity state"
                          value={getCalendarConnectionStateLabel(connection)}
                        />
                      </div>
                      {connection.last_event_ingested_at ? (
                        <p className="mt-2 text-xs text-slate-500">
                          Latest meeting memory landed{" "}
                          {formatDateTime(connection.last_event_ingested_at)}.
                        </p>
                      ) : null}
                      {connection.continuity_summary ? (
                        <p className="mt-2 text-xs text-slate-500">
                          {connection.continuity_summary}
                        </p>
                      ) : null}
                    </div>
                  ))
                ) : (
                  <div className="rounded-[1.2rem] border border-dashed bg-white px-4 py-4 text-sm leading-6 text-slate-600">
                    No calendar is connected yet. Add one above, then bring the
                    next meeting in so Brivoly can prep the conversation from
                    saved context.
                  </div>
                )}
              </div>
              <div className="mt-5 rounded-[1.2rem] border bg-white px-4 py-4">
                <p className="ui-eyebrow">Bring one meeting in</p>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  Use this beta path to attach an upcoming meeting to the right
                  relationship now. Brivoly will fold it into Today, meeting
                  prep, and the relationship timeline.
                </p>
                <div className="mt-4 grid gap-3 xl:grid-cols-2">
                  <input
                    value={calendarEventTitle}
                    onChange={(event) =>
                      setCalendarEventTitle(event.target.value)
                    }
                    placeholder="Weekly rollout review"
                    className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400"
                  />
                  <input
                    value={calendarEventStartsAt}
                    onChange={(event) =>
                      setCalendarEventStartsAt(event.target.value)
                    }
                    type="datetime-local"
                    className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400"
                  />
                  <input
                    value={calendarAttendeeEmails}
                    onChange={(event) =>
                      setCalendarAttendeeEmails(event.target.value)
                    }
                    placeholder="amber@northstarstudio.com, ops@client.com"
                    className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400 xl:col-span-2"
                  />
                  <textarea
                    value={calendarEventNotes}
                    onChange={(event) =>
                      setCalendarEventNotes(event.target.value)
                    }
                    placeholder="Optional notes or agenda from the invite"
                    className="min-h-[120px] w-full rounded-[1.4rem] border border-slate-200 bg-white px-4 py-3 text-sm leading-6 text-slate-800 outline-none transition focus:border-slate-400 xl:col-span-2"
                  />
                </div>
                <div className="mt-4 flex flex-wrap gap-3">
                  <Button
                    disabled={isCalendarPending}
                    onClick={ingestCalendarEvent}
                    className={
                      ambientActionKind === "ingest" &&
                      (connectionFocus === "calendar" ||
                        connectionFocus === "all")
                        ? emphasizedActionClass
                        : undefined
                    }
                  >
                    {isCalendarPending ? "Saving..." : "Save meeting context"}
                  </Button>
                </div>
              </div>
              {calendarStatus ? (
                <p className="mt-4 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700">
                  {calendarStatus}
                </p>
              ) : null}
            </section>

            <section className="mt-6 rounded-[1.4rem] border bg-slate-50/80 p-5">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                Manual thread sync
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                Use this when you want to bring one thread in by hand or test
                relationship memory against a specific message.
              </p>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <input
                  value={inboxThreadId}
                  onChange={(event) => setInboxThreadId(event.target.value)}
                  placeholder="Thread ID (optional)"
                  className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400"
                />
                <input
                  value={inboxSource}
                  onChange={(event) => setInboxSource(event.target.value)}
                  placeholder="Source (gmail, outlook, api)"
                  className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400"
                />
                <input
                  value={inboxCounterpartName}
                  onChange={(event) =>
                    setInboxCounterpartName(event.target.value)
                  }
                  placeholder="Contact name"
                  className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400"
                />
                <input
                  value={inboxCounterpartEmail}
                  onChange={(event) =>
                    setInboxCounterpartEmail(event.target.value)
                  }
                  placeholder="contact@client.com"
                  className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400"
                />
                <input
                  value={inboxSubject}
                  onChange={(event) => setInboxSubject(event.target.value)}
                  placeholder="Thread subject"
                  className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400 md:col-span-2"
                />
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
                      {item === "inbound"
                        ? "Inbound to you"
                        : "Outbound from you"}
                    </button>
                  ))}
                </div>
                <textarea
                  value={inboxMessageBody}
                  onChange={(event) => setInboxMessageBody(event.target.value)}
                  placeholder="Latest email body or key snippet"
                  className="min-h-[150px] w-full rounded-[1.4rem] border border-slate-200 bg-white px-4 py-3 text-sm leading-6 text-slate-800 outline-none transition focus:border-slate-400 md:col-span-2"
                />
              </div>
              <div className="mt-4 flex flex-wrap gap-3">
                <Button disabled={isInboxPending} onClick={syncInboxThread}>
                  {isInboxPending ? "Syncing..." : "Sync thread"}
                </Button>
              </div>
              {inboxStatus ? (
                <p className="mt-4 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700">
                  {inboxStatus}
                </p>
              ) : null}
            </section>

            {selectedLead ? (
              <InboxNextMovePanel
                lead={selectedLead}
                onDraftAction={(draft, threadId) => {
                  setSelectedThreadId(
                    threadId ??
                      selectedLead.recent_email_threads[0]?.thread_id ??
                      null,
                  );
                  generateEmailDraft(draft);
                }}
                isDrafting={isEmailPending}
                draftStatus={emailStatus}
              />
            ) : null}
          </section>

          <InboxActivityPanel
            items={overview.items}
            inboxSummary={overview.inbox_summary}
            selectedLeadId={selectedLead?.id ?? null}
            onSelectLead={(leadId, threadId) => {
              focusLeadForFollowUp(leadId, threadId);
            }}
            onDraftAction={(leadId, draft, threadId) => {
              focusLeadForFollowUp(leadId, threadId);
              requestDraftFocus();
              setQueuedTodayDraft({ leadId, preset: draft });
              void router.push("/clientos/follow-ups");
            }}
            inboxQuery={inboxQuery}
            inboxFilter={inboxFilter}
            onInboxQueryChange={setInboxQuery}
            onInboxFilterChange={setInboxFilter}
            effectiveInboxQuery={deferredInboxQuery}
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
            ambientMemorySummary={overview.ambient_memory_summary}
            onOpenAmbientMemoryAction={openAmbientMemoryAction}
          />
          {overview.relationship_summary ? (
            <RelationshipContinuityPanel
              summary={overview.relationship_summary}
            />
          ) : null}
        </section>
      ) : null}
    </div>
  );
}

function CRMViewHeader({ view }: { view: CRMWorkspaceView }) {
  const copy = {
    overview: {
      eyebrow: "Today",
      title: "Start with the relationship that matters most today.",
      body: "See where attention matters now, what may be slipping, and which warm follow-through is most worth making first.",
    },
    followups: {
      eyebrow: "Relationships",
      title: "Keep the story, the next touch, and the latest context together.",
      body: "Keep notes, recent changes, and the cleanest next move close enough that continuity does not depend on your memory alone.",
    },
    inbox: {
      eyebrow: "Inbox",
      title: "Let email quietly keep the relationship story up to date.",
      body: "Brivoly turns inbox activity into context, summaries, and follow-through without asking you to log everything by hand.",
    },
    pipeline: {
      eyebrow: "Attention",
      title: "Protect quiet relationships before they cool off.",
      body: "Use this page to spot reply pressure, quiet threads, and gentle reopening moments before the relationship drifts too far out of reach.",
    },
    import: {
      eyebrow: "Saved context",
      title:
        "Bring older client context back into the story without extra cleanup.",
      body: "Upload spreadsheets and raw note images, let Brivoly make sense of them, and only keep what supports better follow-through.",
    },
    intake: {
      eyebrow: "Dropzones",
      title: "Give clients one easy place to send context when it matters.",
      body: "Use no-login upload links, simple default paths, and mobile-first capture so updates land in relationship memory without extra back-and-forth.",
    },
  }[view];

  return (
    <section className="mt-6 rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
        {copy.eyebrow}
      </p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">
        {copy.title}
      </h2>
      <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-600">
        {copy.body}
      </p>
    </section>
  );
}

function resolveIntakeTask(pathname: string): CRMIntakeTask {
  if (
    pathname === "/crm/intake/profile" ||
    pathname === "/clientos/intake/profile"
  ) {
    return "profile";
  }
  if (
    pathname === "/crm/intake/routing" ||
    pathname === "/clientos/intake/routing"
  ) {
    return "routing";
  }
  if (
    pathname === "/crm/intake/capture" ||
    pathname === "/clientos/intake/capture"
  ) {
    return "capture";
  }
  return "hub";
}

function TodayPrioritiesPanel({
  items,
  inboxSummary,
  onRunAction,
  ambientMemorySummary,
  onOpenAmbientMemoryAction,
}: {
  items: CRMLeadFollowUp[];
  inboxSummary: CRMFollowUpOverview["inbox_summary"];
  onRunAction: (
    leadId: string,
    route: string,
    preset?: TodayDraftPreset,
    memoryView?: "meeting_prep",
    threadId?: string | null,
  ) => void;
  ambientMemorySummary: CRMFollowUpOverview["ambient_memory_summary"];
  onOpenAmbientMemoryAction: (route: string) => void;
}) {
  const replyLead =
    [...items]
      .filter((item) =>
        item.recent_email_threads.some((thread) => thread.needs_reply),
      )
      .sort((left, right) => compareReplyPriority(left, right))[0] ?? null;
  const reconnectLead =
    [...items]
      .filter(
        (item) =>
          item.relationship_state === "stale" ||
          item.relationship_state === "at_risk" ||
          item.relationship_state === "drifting",
      )
      .sort((left, right) => compareReconnectPriority(left, right))[0] ?? null;
  const proposalLead =
    [...items]
      .filter((item) => isProposalFollowThrough(item))
      .sort((left, right) => compareProposalPriority(left, right))[0] ?? null;
  const recentUploadLead =
    [...items]
      .filter((item) => hasRecentUploadContext(item))
      .sort((left, right) => compareRecentUploadPriority(left, right))[0] ??
    null;
  const recentContextLead =
    [...items]
      .filter((item) => hasFreshContext(item) && !hasRecentUploadContext(item))
      .sort((left, right) => compareFreshContextPriority(left, right))[0] ??
    null;
  const meetingLead =
    [...items]
      .filter((item) => item.relationship_upcoming_meeting_at)
      .sort(
        (left, right) =>
          new Date(
            left.relationship_upcoming_meeting_at ?? left.next_follow_up_at,
          ).getTime() -
          new Date(
            right.relationship_upcoming_meeting_at ?? right.next_follow_up_at,
          ).getTime(),
      )[0] ?? null;
  const replyThread = replyLead ? getReplyThread(replyLead) : null;

  const uploadReentryLead =
    recentUploadLead && isReconnectMoment(recentUploadLead)
      ? recentUploadLead
      : null;

  const priorities = compactPriorityCards<TodayPriorityCardItem>([
    uploadReentryLead
      ? {
          id: `${uploadReentryLead.id}-upload-reconnect`,
          href: "/clientos/follow-ups",
          eyebrow: "Fresh way back in",
          title: `Use new context to reopen ${uploadReentryLead.lead_name}`,
          body:
            uploadReentryLead.relationship_reconnect_why_now ||
            uploadReentryLead.relationship_upload_follow_through_hint ||
            uploadReentryLead.relationship_recent_upload_summary,
          meta: `${uploadReentryLead.company_name} · ${formatDateTime(getLatestUploadContextEntry(uploadReentryLead)?.occurred_at ?? null)}`,
          nextMove:
            uploadReentryLead.relationship_reconnect_next_move ||
            uploadReentryLead.relationship_upload_follow_through_hint ||
            "Use the fresh context to restart the thread gently.",
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
          body:
            replyThread?.next_touch_hint ||
            replyThread?.memory_summary ||
            getReplySummary(replyLead),
          meta: `${replyLead.company_name} · ${formatDateTime(getNewestThreadTime(replyLead) ?? replyLead.next_follow_up_at)}`,
          nextMove:
            replyThread?.open_loop ||
            replyThread?.carry_forward_hint ||
            "Pick up the thread while the context is still fresh.",
          actionLabel: "Draft reply",
          onAction: () =>
            onRunAction(
              replyLead.id,
              "/clientos/follow-ups",
              {
                objective: "follow_up",
                tone: "warm",
                length: "short",
                status: "Drafting a reply from Today...",
              },
              undefined,
              replyThread?.thread_id ?? null,
            ),
        }
      : null,
    meetingLead
      ? {
          id: `${meetingLead.id}-meeting`,
          href: "/clientos/follow-ups",
          eyebrow: "Meeting prep",
          title: `Prepare for ${meetingLead.lead_name}`,
          body:
            meetingLead.relationship_meeting_prep_summary ||
            meetingLead.relationship_upcoming_meeting_label ||
            meetingLead.next_step,
          meta: `${meetingLead.company_name} · ${formatDateTime(meetingLead.relationship_upcoming_meeting_at ?? meetingLead.next_follow_up_at)}`,
          nextMove:
            meetingLead.relationship_upcoming_meeting_label ||
            "Open the relationship and walk in with the right context already in view.",
          memoryView: "meeting_prep",
          actionLabel: "Prepare now",
          onAction: () =>
            onRunAction(
              meetingLead.id,
              "/clientos/follow-ups",
              undefined,
              "meeting_prep",
            ),
        }
      : null,
    reconnectLead && reconnectLead.id !== uploadReentryLead?.id
      ? {
          id: `${reconnectLead.id}-reconnect`,
          href: "/clientos/follow-ups",
          eyebrow: "Reconnect",
          title: `Reconnect with ${reconnectLead.lead_name}`,
          body:
            reconnectLead.relationship_reconnect_why_now ||
            reconnectLead.relationship_timing_nudge ||
            reconnectLead.relationship_reminders[0]?.message ||
            reconnectLead.next_step,
          meta: `${reconnectLead.company_name} · last meaningful touch ${formatDateTime(reconnectLead.last_meaningful_interaction_at)}`,
          nextMove:
            reconnectLead.relationship_reconnect_next_move ||
            reconnectLead.relationship_reconnect_message_hint ||
            "Use a short, low-pressure check-in.",
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
          body:
            proposalLead.relationship_timing_nudge || proposalLead.next_step,
          meta: `${proposalLead.company_name} · follow up by ${formatDateTime(proposalLead.next_follow_up_at)}`,
          nextMove:
            proposalLead.next_step ||
            "Send the lightest possible nudge that moves the thread forward.",
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
          eyebrow: isReconnectMoment(recentUploadLead)
            ? "Fresh way back in"
            : "Fresh client update",
          title: isReconnectMoment(recentUploadLead)
            ? `Use new context to reopen ${recentUploadLead.lead_name}`
            : `Follow up on new context from ${recentUploadLead.lead_name}`,
          body:
            (isReconnectMoment(recentUploadLead)
              ? recentUploadLead.relationship_reconnect_why_now ||
                recentUploadLead.relationship_upload_follow_through_hint
              : undefined) ||
            recentUploadLead.relationship_upload_follow_through_hint ||
            `${recentUploadLead.relationship_recent_upload_summary}${recentUploadLead.next_step.trim() ? ` Next touch: ${recentUploadLead.next_step}` : ""}`,
          meta: `${recentUploadLead.company_name} · ${formatDateTime(getLatestUploadContextEntry(recentUploadLead)?.occurred_at ?? null)}`,
          nextMove:
            recentUploadLead.relationship_upload_follow_through_hint ||
            recentUploadLead.relationship_reconnect_next_move ||
            "Turn the fresh client context into a quick follow-through note.",
          actionLabel: isReconnectMoment(recentUploadLead)
            ? "Draft reconnect"
            : "Draft note",
          onAction: () =>
            onRunAction(recentUploadLead.id, "/clientos/follow-ups", {
              objective: isReconnectMoment(recentUploadLead)
                ? "revive"
                : "recap",
              tone: "warm",
              length: "short",
              status: isReconnectMoment(recentUploadLead)
                ? "Drafting a reconnect from fresh client context..."
                : "Drafting a note from fresh client context...",
            }),
        }
      : null,
    recentContextLead
      ? {
          id: `${recentContextLead.id}-context`,
          href: "/clientos/follow-ups",
          eyebrow: "Fresh context",
          title: `New context from ${recentContextLead.lead_name}`,
          body:
            getLatestContextEntry(recentContextLead)?.summary ??
            recentContextLead.notes,
          meta: `${recentContextLead.company_name} · ${formatDateTime(getLatestContextEntry(recentContextLead)?.occurred_at ?? null)}`,
          nextMove:
            recentContextLead.next_step ||
            "Open the relationship and decide whether this changes the next touch.",
          actionLabel: "Open relationship",
          onAction: () =>
            onRunAction(recentContextLead.id, "/clientos/follow-ups"),
        }
      : null,
  ]);

  const fallbackPriorities: TodayPriorityCardItem[] = [...items]
    .sort((left, right) => compareAttentionPriority(left, right))
    .slice(0, 4)
    .map((item) => ({
      id: item.id,
      href: "/clientos/follow-ups",
      eyebrow: "Next touch",
      title: summarizePriority(item),
      body: item.next_step,
      meta: `${item.lead_name} · ${formatDateTime(item.next_follow_up_at)}`,
      nextMove:
        item.relationship_timing_nudge ||
        "Open the relationship and take the smallest useful next step.",
    }));
  const visiblePriorities = (
    priorities.length ? priorities : fallbackPriorities
  ).slice(0, 4);
  const primaryPriority = visiblePriorities[0] ?? null;
  const secondaryPriorities = visiblePriorities.slice(1);

  const replyCount = inboxSummary?.needs_reply_count ?? 0;
  const atRiskCount = items.filter(
    (item) => item.relationship_state === "at_risk",
  ).length;
  const staleCount = items.filter(
    (item) => item.relationship_state === "stale",
  ).length;
  const driftingCount = items.filter(
    (item) => item.relationship_state === "drifting",
  ).length;
  const meetingCount = items.filter(
    (item) => item.relationship_upcoming_meeting_at,
  ).length;
  const reconnectCount = atRiskCount + staleCount + driftingCount;
  const proposalCount = items.filter((item) =>
    isProposalFollowThrough(item),
  ).length;
  const recentUploadCount = items.filter((item) =>
    hasRecentUploadContext(item),
  ).length;
  const freshContextCount = items.filter((item) =>
    hasFreshContext(item),
  ).length;
  const urgentCount = replyCount + proposalCount + reconnectCount;
  const contextCount =
    recentUploadCount + Math.max(0, freshContextCount - recentUploadCount);
  const memoryCoverageLine =
    ambientMemorySummary?.continuity_summary ||
    "Connect an inbox or calendar once and Brivoly can keep more of this context warm for you.";
  const focusMoves = compactPriorityCards<TodayFocusMove>([
    replyLead
      ? {
          id: `${replyLead.id}-reply-focus`,
          label: "Reply soon",
          title: `${replyLead.lead_name} is waiting on you`,
          body:
            replyThread?.open_loop ||
            replyThread?.next_touch_hint ||
            getReplySummary(replyLead),
          actionLabel: "Draft reply",
          onAction: () =>
            onRunAction(
              replyLead.id,
              "/clientos/follow-ups",
              {
                objective: "follow_up",
                tone: "warm",
                length: "short",
                status: "Drafting a reply from Today...",
              },
              undefined,
              replyThread?.thread_id ?? null,
            ),
        }
      : null,
    reconnectLead
      ? {
          id: `${reconnectLead.id}-reconnect-focus`,
          label: "Reconnect gently",
          title: `${reconnectLead.lead_name} has a soft way back in`,
          body:
            reconnectLead.relationship_reconnect_why_now ||
            reconnectLead.relationship_reconnect_next_move ||
            reconnectLead.next_step,
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
          id: `${proposalLead.id}-proposal-focus`,
          label: "Proposal follow-through",
          title: `${proposalLead.lead_name} needs momentum, not a long chase`,
          body:
            proposalLead.next_step ||
            proposalLead.relationship_timing_nudge ||
            "Keep the proposal thread moving with one confident nudge.",
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
    recentUploadLead
      ? {
          id: `${recentUploadLead.id}-upload-focus`,
          label: "Fresh client update",
          title: `${recentUploadLead.lead_name} gave you new context to use`,
          body:
            recentUploadLead.relationship_upload_follow_through_hint ||
            recentUploadLead.relationship_recent_upload_summary ||
            recentUploadLead.next_step,
          actionLabel: isReconnectMoment(recentUploadLead)
            ? "Draft reconnect"
            : "Draft note",
          onAction: () =>
            onRunAction(recentUploadLead.id, "/clientos/follow-ups", {
              objective: isReconnectMoment(recentUploadLead)
                ? "revive"
                : "recap",
              tone: "warm",
              length: "short",
              status: isReconnectMoment(recentUploadLead)
                ? "Drafting a reconnect from fresh client context..."
                : "Drafting a note from fresh client context...",
            }),
        }
      : null,
  ]).slice(0, 4);
  const laterLead =
    [...items]
      .filter(
        (item) =>
          !item.recent_email_threads.some((thread) => thread.needs_reply) &&
          !isReconnectMoment(item) &&
          !isProposalFollowThrough(item) &&
          !hasRecentUploadContext(item),
      )
      .sort((left, right) => compareSoonestFollowUp(left, right))[0] ?? null;
  const quickRhythm = compactPriorityCards<TodayRhythmStep>([
    primaryPriority
      ? {
          id: `${primaryPriority.id}-rhythm-first`,
          label: "First few minutes",
          title: primaryPriority.title,
          body: primaryPriority.nextMove || primaryPriority.body,
        }
      : null,
    secondaryPriorities[0]
      ? {
          id: `${secondaryPriorities[0].id}-rhythm-next`,
          label: "If you have a little more time",
          title: secondaryPriorities[0].title,
          body: secondaryPriorities[0].nextMove || secondaryPriorities[0].body,
        }
      : null,
    laterLead
      ? {
          id: `${laterLead.id}-rhythm-later`,
          label: "What can wait",
          title: `${laterLead.lead_name} can stay warm quietly`,
          body:
            laterLead.relationship_timing_nudge ||
            laterLead.next_step ||
            "Brivoly can keep holding this until you have more room.",
        }
      : null,
  ]).slice(0, 3);

  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
        Today’s priorities
      </p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">
        Your daily starting point.
      </h2>
      <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
        Brivoly pulls together replies, reconnects, proposal follow-through,
        meeting prep, and fresh client context so the first move is obvious
        without re-reading everything first.
      </p>
      <p className="mt-3 text-sm font-medium text-slate-700">
        Start with one relationship and one next move. Brivoly will hold the
        rest.
      </p>
      <p className="mt-2 text-sm leading-6 text-slate-600">
        {memoryCoverageLine}
      </p>
      {ambientMemorySummary?.warm_source_labels?.length ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {ambientMemorySummary.warm_source_labels.map((label) => (
            <span
              key={`warm-${label}`}
              className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-800"
            >
              Warm: {label}
            </span>
          ))}
        </div>
      ) : null}
      {ambientMemorySummary?.quiet_source_labels?.length ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {ambientMemorySummary.quiet_source_labels.map((label) => (
            <span
              key={`quiet-${label}`}
              className="rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-medium text-sky-800"
            >
              Quiet: {label}
            </span>
          ))}
        </div>
      ) : null}
      {ambientMemorySummary?.attention_source_labels?.length ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {ambientMemorySummary.attention_source_labels.map((label) => (
            <span
              key={`attention-${label}`}
              className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-800"
            >
              Needs care: {label}
            </span>
          ))}
        </div>
      ) : ambientMemorySummary?.paused_source_labels?.length ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {ambientMemorySummary.paused_source_labels.map((label) => (
            <span
              key={`paused-${label}`}
              className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-700"
            >
              Paused: {label}
            </span>
          ))}
        </div>
      ) : null}
      {ambientMemorySummary?.suggested_action_label &&
      ambientMemorySummary.suggested_action_route ? (
        <div className="mt-3">
          <button
            type="button"
            onClick={() =>
              onOpenAmbientMemoryAction(
                ambientMemorySummary.suggested_action_route,
              )
            }
            className="rounded-full border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-700 transition hover:border-slate-400 hover:bg-white hover:text-slate-950"
          >
            {ambientMemorySummary.suggested_action_label}
          </button>
          {ambientMemorySummary.suggested_action_note ? (
            <p className="mt-2 text-xs leading-5 text-slate-500">
              {ambientMemorySummary.suggested_action_note}
            </p>
          ) : null}
        </div>
      ) : null}
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
            Jump to {item.actionLabel?.toLowerCase() ?? item.eyebrow.toLowerCase()}
          </button>
        ))}
      </div>
      {focusMoves.length ? (
        <div className="mt-5 rounded-[1.35rem] border bg-slate-50/80 px-5 py-4">
          <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                Keep close
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                These are the warmest openings across replies, reconnects,
                proposals, and new client context.
              </p>
            </div>
            <p className="text-xs text-slate-500">
              One quick move in each lane is enough.
            </p>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {focusMoves.map((item) => (
              <div
                key={item.id}
                className="rounded-[1rem] border bg-white px-4 py-4"
              >
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                  {item.label}
                </p>
                <p className="mt-2 text-sm font-medium text-slate-900">
                  {item.title}
                </p>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  {item.body}
                </p>
                <div className="mt-4">
                  <button
                    type="button"
                    onClick={item.onAction}
                    className="rounded-full border border-slate-300 bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-slate-700 transition hover:border-slate-500 hover:text-slate-950"
                  >
                    {item.actionLabel}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
      {quickRhythm.length ? (
        <div className="mt-5 rounded-[1.35rem] border bg-white px-5 py-4">
          <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                A calm rhythm for today
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                If you only have a short window, move through the day in this
                order and let Brivoly hold the rest.
              </p>
            </div>
            <p className="text-xs text-slate-500">
              One move is enough to make the day feel lighter.
            </p>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            {quickRhythm.map((step) => (
              <div
                key={step.id}
                className="rounded-[1rem] border bg-slate-50/70 px-4 py-4"
              >
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                  {step.label}
                </p>
                <p className="mt-2 text-sm font-medium text-slate-900">
                  {step.title}
                </p>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  {step.body}
                </p>
              </div>
            ))}
          </div>
        </div>
      ) : null}
      <div className="mt-5 grid gap-3 md:grid-cols-3">
        <TodaySignal
          label="Needs care now"
          value={urgentCount ? String(urgentCount) : "Clear"}
          detail={
            urgentCount
              ? `${replyCount ? `${replyCount} repl${replyCount === 1 ? "y" : "ies"}` : "no replies"}, ${atRiskCount ? `${atRiskCount} at-risk relationship${atRiskCount === 1 ? "" : "s"}` : "no at-risk relationships"}, ${staleCount + driftingCount ? `${staleCount + driftingCount} reopening moment${staleCount + driftingCount === 1 ? "" : "s"}` : "no reopening moments"}, and ${proposalCount ? `${proposalCount} proposal follow-up${proposalCount === 1 ? "" : "s"}` : "no proposal nudges"}`
              : "Nothing urgent is stacking up right now"
          }
        />
        <TodaySignal
          label="Freshest opening"
          value={
            meetingCount
              ? String(meetingCount)
              : contextCount
                ? String(contextCount)
                : "Quiet"
          }
          detail={
            meetingCount
              ? `${meetingCount} meeting prep moment${meetingCount === 1 ? "" : "s"} is coming up soon`
              : recentUploadCount
                ? `${recentUploadCount} client upload${recentUploadCount === 1 ? "" : "s"} landed recently`
                : freshContextCount
                  ? `${freshContextCount} relationship${freshContextCount === 1 ? "" : "s"} picked up new context recently`
                  : "No new client context landed overnight"
          }
        />
        {ambientMemorySummary ? (
          <TodaySignal
            label="Background memory"
            value={formatAmbientContinuityState(
              ambientMemorySummary.continuity_state,
            )}
            detail={ambientMemorySummary.continuity_summary}
          />
        ) : null}
      </div>
      {primaryPriority ? (
        <div className="mt-5 rounded-[1.5rem] border border-slate-900 bg-slate-950 px-5 py-5 text-white shadow-sm">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-2xl">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-200">
                Start here
              </p>
              <p className="mt-2 text-2xl font-semibold tracking-tight">
                {primaryPriority.title}
              </p>
              <p className="mt-3 text-sm leading-6 text-slate-200">
                {primaryPriority.body}
              </p>
              {primaryPriority.nextMove ? (
                <div className="mt-4 rounded-[1rem] border border-white/10 bg-white/5 px-4 py-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-200">
                    Next move
                  </p>
                  <p className="mt-2 text-sm leading-6 text-slate-100">
                    {primaryPriority.nextMove}
                  </p>
                </div>
              ) : null}
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <TimelineTileDark
                  label="Why now"
                  value={
                    items.find((item) => primaryPriority.id.startsWith(item.id))
                      ? getLeadCardWhyNow(
                          items.find((item) =>
                            primaryPriority.id.startsWith(item.id),
                          )!,
                        )
                      : primaryPriority.body
                  }
                />
                <TimelineTileDark
                  label="Latest saved moment"
                  value={
                    items.find((item) => primaryPriority.id.startsWith(item.id))
                      ? getLeadCardStory(
                          items.find((item) =>
                            primaryPriority.id.startsWith(item.id),
                          )!,
                        )
                      : primaryPriority.meta
                  }
                />
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-300">
                Take the smallest next step here first, then let Brivoly hold
                the rest of the context in place.
              </p>
              <p className="mt-4 text-xs text-slate-300">
                {primaryPriority.meta}
              </p>
              <p className="mt-3 text-xs uppercase tracking-[0.16em] text-slate-400">
                {primaryPriority.eyebrow}
              </p>
            </div>
            <div className="flex flex-wrap gap-2 lg:justify-end">
              <Button
                type="button"
                onClick={primaryPriority.onAction}
                className="border border-white/20 bg-white text-slate-950 hover:bg-slate-100"
              >
                {primaryPriority.actionLabel ?? "Open"}
              </Button>
              <Button
                asChild
                variant="outline"
                className="border-white/20 bg-transparent text-white hover:bg-white/10 hover:text-white"
              >
                <Link href={primaryPriority.href}>Open relationship</Link>
              </Button>
            </div>
          </div>
        </div>
      ) : null}
      {secondaryPriorities.length ? (
        <div className="mt-5 rounded-[1.35rem] border bg-slate-50/80 px-5 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
            After that
          </p>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            {secondaryPriorities.slice(0, 2).map((item) => (
              <div
                key={`${item.id}-after`}
                className="rounded-[1rem] border bg-white px-4 py-4"
              >
                <p className="text-sm font-medium text-slate-900">
                  {item.title}
                </p>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  {item.nextMove || item.body}
                </p>
                <p className="mt-3 text-xs text-slate-500">{item.meta}</p>
              </div>
            ))}
          </div>
        </div>
      ) : null}
      {secondaryPriorities.length ? (
        <div className="mt-5">
          <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                Then keep moving
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                Once the first move is handled, these are the next warm openings
                Brivoly would keep close.
              </p>
            </div>
            <p className="text-xs text-slate-500">
              Keep this list short. One move at a time is enough.
            </p>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
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
        </div>
      ) : null}
      <div className="mt-5 flex flex-wrap gap-3">
        <QuickLinkPill
          href="/clientos/follow-ups"
          title="Relationships"
          body="Keep the last touch, the next touch, and the full story together."
        />
        <QuickLinkPill
          href="/clientos/inbox"
          title="Inbox"
          body="Let email carry the thread forward without extra logging."
        />
      </div>
    </section>
  );
}

function TodaySignal({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="min-w-0 overflow-hidden rounded-[1.2rem] border bg-slate-50/80 px-5 py-5">
      <div className="flex items-start justify-between gap-4">
        <p className="max-w-[16rem] break-words text-xs font-semibold uppercase tracking-[0.14em] text-slate-400 [overflow-wrap:anywhere] sm:tracking-[0.18em]">
          {label}
        </p>
        <p className="shrink-0 text-3xl font-semibold tracking-tight text-slate-950">
          {value}
        </p>
      </div>
      <p className="mt-4 max-w-[24rem] break-words text-sm leading-6 text-slate-700 [overflow-wrap:anywhere]">
        {detail}
      </p>
    </div>
  );
}

function DailyFlowCard({
  label,
  title,
  body,
  tone,
}: {
  label: string;
  title: string;
  body: string;
  tone: "primary" | "secondary" | "neutral";
}) {
  const className =
    tone === "primary"
      ? "border-slate-900 bg-slate-950 text-white"
      : tone === "secondary"
        ? "border-sky-200 bg-sky-50 text-slate-950"
        : "border-slate-200 bg-slate-50 text-slate-950";
  const eyebrowClass = tone === "primary" ? "text-cyan-200" : "text-slate-500";
  const bodyClass = tone === "primary" ? "text-slate-200" : "text-slate-600";

  return (
    <div className={`rounded-[1.35rem] border px-4 py-4 ${className}`}>
      <p
        className={`text-xs font-semibold uppercase tracking-[0.16em] ${eyebrowClass}`}
      >
        {label}
      </p>
      <p className="mt-3 text-lg font-semibold tracking-tight">{title}</p>
      <p className={`mt-3 text-sm leading-6 ${bodyClass}`}>{body}</p>
    </div>
  );
}

function formatAmbientContinuityState(value: string): string {
  if (value === "attention_needed") {
    return "Needs care";
  }
  if (value === "waiting") {
    return "Waiting";
  }
  if (value === "paused") {
    return "Paused";
  }
  if (value === "warm") {
    return "Warm";
  }
  return "Offline";
}

function mailboxNeedsReconnect(connection: CRMMailboxConnection) {
  return connection.reauth_required || connection.status === "needs_reauth";
}

function isMailboxQuiet(connection: CRMMailboxConnection) {
  return (
    connection.background_sync_enabled &&
    connection.status === "connected" &&
    !mailboxNeedsReconnect(connection) &&
    (connection.sync_stale ||
      (connection.connection_mode === "oauth" &&
        !connection.event_ready &&
        connection.watch_status !== "manual"))
  );
}

function getMailboxConnectionStateLabel(connection: CRMMailboxConnection) {
  if (mailboxNeedsReconnect(connection)) {
    return "Reconnect this inbox";
  }
  if (!connection.background_sync_enabled) {
    return "Inbox memory paused";
  }
  if (connection.event_ready) {
    return "Event-ready inbox memory";
  }
  if (isMailboxQuiet(connection)) {
    return "Quiet inbox memory";
  }
  if (connection.connection_mode === "manual") {
    return "Manual inbox preview";
  }
  return "Inbox memory on";
}

function getMailboxConnectionStateDetail(connection: CRMMailboxConnection) {
  if (mailboxNeedsReconnect(connection)) {
    return (
      connection.health_note ||
      "Brivoly cannot quietly refresh this inbox until you reconnect it."
    );
  }
  if (!connection.background_sync_enabled) {
    return "This inbox is saved, but Brivoly is not pulling fresh thread memory from it right now.";
  }
  if (connection.event_ready) {
    return "This inbox is ready to warm relationship memory from new provider events as they land.";
  }
  if (isMailboxQuiet(connection)) {
    return "This inbox is connected, but Brivoly is waiting for a fresh provider event or sync to warm the thread memory back up.";
  }
  if (connection.connection_mode === "manual") {
    return "This inbox is still on the manual path, so Brivoly can help with continuity but cannot quietly follow live provider events yet.";
  }
  return (
    connection.continuity_summary ||
    "This inbox is connected and ready for the next thread memory update."
  );
}

function getMailboxConnectionFix(connection: CRMMailboxConnection) {
  if (mailboxNeedsReconnect(connection)) {
    return "Reconnect this inbox first so Brivoly can resume quiet thread continuity.";
  }
  if (!connection.background_sync_enabled) {
    return "Resume inbox memory when you want fresh thread context to start flowing back in.";
  }
  if (connection.connection_mode === "manual") {
    return "Keep this as a fallback, or connect the real provider account when you want event-ready continuity.";
  }
  if (connection.watch_status === "manual") {
    return "Use Sync now when you want a fresh read. Outlook still relies on sync jobs more than watch coverage here.";
  }
  if (!connection.event_ready) {
    return "Refresh watch coverage or run one sync so the next live thread can warm this memory back up.";
  }
  return "No fix needed. Brivoly should quietly keep this inbox in the background.";
}

function getMailboxWatchRead(connection: CRMMailboxConnection) {
  if (connection.connection_mode === "manual") {
    return "Manual inboxes do not use provider watch coverage yet.";
  }
  if (mailboxNeedsReconnect(connection)) {
    return "Watch coverage is blocked until this inbox is reconnected.";
  }
  if (connection.watch_status === "active") {
    return connection.last_watch_event_at
      ? `Active and already saw a provider event ${formatDateTime(connection.last_watch_event_at)}.`
      : "Active and waiting for the next provider event.";
  }
  if (connection.watch_status === "manual") {
    return "This inbox is still relying on scheduled sync instead of live watch events.";
  }
  return "Watch coverage is not warm yet. Refresh it or sync once to settle the continuity layer.";
}

function calendarNeedsAttention(connection: CRMCalendarConnection) {
  return connection.status !== "" && connection.status !== "connected";
}

function isCalendarQuiet(connection: CRMCalendarConnection) {
  return (
    connection.background_sync_enabled &&
    connection.status === "connected" &&
    !connection.memory_warm &&
    connection.sync_stale
  );
}

function getCalendarConnectionStateLabel(connection: CRMCalendarConnection) {
  if (calendarNeedsAttention(connection)) {
    return "Check this calendar";
  }
  if (!connection.background_sync_enabled) {
    return "Meeting memory paused";
  }
  if (connection.memory_warm) {
    return "Meeting memory warm";
  }
  if (isCalendarQuiet(connection)) {
    return "Meeting memory quiet";
  }
  return "Meeting memory on";
}

function getCalendarConnectionStateDetail(connection: CRMCalendarConnection) {
  if (calendarNeedsAttention(connection)) {
    return (
      connection.health_note ||
      "This calendar needs attention before Brivoly can quietly hold meeting context from it again."
    );
  }
  if (!connection.background_sync_enabled) {
    return "This calendar is saved, but Brivoly is not using it for fresh meeting prep right now.";
  }
  if (connection.memory_warm) {
    return "This calendar recently fed meeting context into relationship memory, so prep moments should stay easier to trust.";
  }
  if (isCalendarQuiet(connection)) {
    return "This calendar is connected, but no fresh meeting context has landed recently enough to keep prep warm.";
  }
  return (
    connection.continuity_summary ||
    "This calendar is connected and waiting for the next useful meeting context."
  );
}

function getCalendarConnectionFix(connection: CRMCalendarConnection) {
  if (calendarNeedsAttention(connection)) {
    return "Check this calendar connection first so Brivoly can warm meeting prep quietly again.";
  }
  if (!connection.background_sync_enabled) {
    return "Resume meeting memory when you want Brivoly to start pulling prep context back in.";
  }
  if (isCalendarQuiet(connection)) {
    return "Bring one upcoming meeting in or wait for the next event so Brivoly has fresh prep context to hold.";
  }
  return "No fix needed. Brivoly should keep using this calendar quietly in the background.";
}

function getCalendarWarmthRead(connection: CRMCalendarConnection) {
  if (connection.last_event_ingested_at) {
    return `Latest meeting memory landed ${formatDateTime(connection.last_event_ingested_at)}.`;
  }
  if (connection.last_sync_at) {
    return `This calendar last checked in ${formatDateTime(connection.last_sync_at)}, but no fresh meeting context has landed yet.`;
  }
  return "No meeting context has been saved from this calendar yet.";
}

function QuickLinkPill({
  href,
  title,
  body,
}: {
  href: string;
  title: string;
  body: string;
}) {
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

function RelationshipContinuityPanel({
  summary,
}: {
  summary: NonNullable<CRMFollowUpOverview["relationship_summary"]>;
}) {
  const steadyCount = summary.active_count + summary.warm_count;
  const needsCareCount =
    summary.drifting_count + summary.stale_count + summary.at_risk_count;
  const warmMoments =
    summary.referral_reminder_count + summary.milestone_reminder_count;
  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
        Relationship continuity
      </p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">
        Stay warm without holding everything in your head.
      </h2>
      <div className="mt-5 rounded-[1.3rem] border bg-slate-50/80 px-5 py-5">
        <p className="text-sm leading-7 text-slate-700">
          <span className="font-semibold text-slate-950">{steadyCount}</span>{" "}
          relationship{steadyCount === 1 ? "" : "s"} still feel steady.{" "}
          {needsCareCount ? (
            <>
              <span className="font-semibold text-slate-950">
                {needsCareCount}
              </span>{" "}
              may need a warmer touch soon.
            </>
          ) : (
            "Nothing feels especially fragile right now."
          )}{" "}
          {summary.warm_intro_connections.length
            ? `${summary.warm_intro_connections.length} warm re-entry path${summary.warm_intro_connections.length === 1 ? "" : "s"} could help reopen a thread more naturally.`
            : ""}{" "}
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
        <p className="break-words text-xs font-semibold uppercase tracking-[0.14em] text-slate-400 [overflow-wrap:anywhere] sm:tracking-[0.18em]">
          {eyebrow}
        </p>
        <p className="break-words text-lg font-semibold tracking-tight text-slate-950 [overflow-wrap:anywhere]">
          {title}
        </p>
        <p className="mt-2 break-words text-sm leading-6 text-slate-600 [overflow-wrap:anywhere]">
          {body}
        </p>
        {nextMove ? (
          <p className="mt-3 break-words text-sm leading-6 text-slate-800 [overflow-wrap:anywhere]">
            <span className="font-medium text-slate-950">Next move:</span>{" "}
            {nextMove}
          </p>
        ) : null}
        <p className="mt-3 break-words text-xs text-slate-500 [overflow-wrap:anywhere]">
          {meta}
        </p>
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
  ambientMemorySummary,
  onOpenAmbientMemoryAction,
}: {
  summary: CRMPipelineStageSummary[];
  items: CRMLeadFollowUp[];
  selectedLeadId: string | null;
  onSelectLead: (leadId: string) => void;
  onRunAction: (
    leadId: string,
    route: string,
    preset?: TodayDraftPreset,
  ) => void;
  ambientMemorySummary: CRMFollowUpOverview["ambient_memory_summary"];
  onOpenAmbientMemoryAction: (route: string) => void;
}) {
  const itemsByStage = new Map<string, CRMLeadFollowUp[]>();
  for (const item of items) {
    const bucket = itemsByStage.get(item.stage) ?? [];
    bucket.push(item);
    itemsByStage.set(item.stage, bucket);
  }
  const needsCareFirst = [...items]
    .filter(
      (item) =>
        relationshipStateUrgency(item.relationship_state) > 0 ||
        item.recent_email_threads.some((thread) => thread.needs_reply),
    )
    .sort((left, right) => compareAttentionPriority(left, right))
    .slice(0, 4);
  const primaryFragile = needsCareFirst[0] ?? null;
  const memoryCoverageLine =
    ambientMemorySummary?.continuity_summary ||
    "Connect an inbox or calendar if you want quiet continuity to show up here with less manual work.";

  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm xl:col-span-2">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-2xl">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
            Relationship attention
          </p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">
            Protect the relationships that are easiest to lose.
          </h2>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            This page is for quiet threads, overdue replies, and gentle re-entry
            moments. The goal is continuity and warmth, not system-heavy
            tracking.
          </p>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            {memoryCoverageLine}
          </p>
          {ambientMemorySummary?.warm_source_labels?.length ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {ambientMemorySummary.warm_source_labels.map((label) => (
                <span
                  key={`warm-${label}`}
                  className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-800"
                >
                  Warm: {label}
                </span>
              ))}
            </div>
          ) : null}
          {ambientMemorySummary?.quiet_source_labels?.length ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {ambientMemorySummary.quiet_source_labels.map((label) => (
                <span
                  key={`quiet-${label}`}
                  className="rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-medium text-sky-800"
                >
                  Quiet: {label}
                </span>
              ))}
            </div>
          ) : null}
          {ambientMemorySummary?.attention_source_labels?.length ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {ambientMemorySummary.attention_source_labels.map((label) => (
                <span
                  key={`attention-${label}`}
                  className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-800"
                >
                  Needs care: {label}
                </span>
              ))}
            </div>
          ) : ambientMemorySummary?.paused_source_labels?.length ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {ambientMemorySummary.paused_source_labels.map((label) => (
                <span
                  key={`paused-${label}`}
                  className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-700"
                >
                  Paused: {label}
                </span>
              ))}
            </div>
          ) : null}
          {ambientMemorySummary?.suggested_action_label &&
          ambientMemorySummary.suggested_action_route ? (
            <div className="mt-3">
              <button
                type="button"
                onClick={() =>
                  onOpenAmbientMemoryAction(
                    ambientMemorySummary.suggested_action_route,
                  )
                }
                className="rounded-full border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-700 transition hover:border-slate-400 hover:bg-white hover:text-slate-950"
              >
                {ambientMemorySummary.suggested_action_label}
              </button>
              {ambientMemorySummary.suggested_action_note ? (
                <p className="mt-2 text-xs leading-5 text-slate-500">
                  {ambientMemorySummary.suggested_action_note}
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
        <div className="grid gap-3 lg:max-w-md lg:grid-cols-2">
          <CompactMetricLight
            label="Reply pressure"
            value={`${items.filter((item) => item.recent_email_threads.some((thread) => thread.needs_reply)).length} thread${items.filter((item) => item.recent_email_threads.some((thread) => thread.needs_reply)).length === 1 ? "" : "s"}`}
            tone={
              items.some((item) =>
                item.recent_email_threads.some((thread) => thread.needs_reply),
              )
                ? "critical"
                : "neutral"
            }
          />
          <CompactMetricLight
            label="At risk now"
            value={`${items.filter((item) => item.relationship_state === "at_risk").length} relationship${items.filter((item) => item.relationship_state === "at_risk").length === 1 ? "" : "s"}`}
            tone={
              items.some((item) => item.relationship_state === "at_risk")
                ? "critical"
                : "neutral"
            }
          />
          <CompactMetricLight
            label="Quiet enough to reopen"
            value={`${items.filter((item) => item.relationship_state === "stale" || item.relationship_state === "drifting").length} relationship${items.filter((item) => item.relationship_state === "stale" || item.relationship_state === "drifting").length === 1 ? "" : "s"}`}
            tone={
              items.some(
                (item) =>
                  item.relationship_state === "stale" ||
                  item.relationship_state === "drifting",
              )
                ? "warning"
                : "neutral"
            }
          />
          <CompactMetricLight
            label="Warm openings"
            value={`${summary.reduce((total, stage) => total + stage.high_priority_count, 0)} relationship${summary.reduce((total, stage) => total + stage.high_priority_count, 0) === 1 ? "" : "s"}`}
            tone={
              summary.reduce(
                (total, stage) => total + stage.high_priority_count,
                0,
              )
                ? "positive"
                : "neutral"
            }
          />
        </div>
      </div>

      {primaryFragile ? (
        <div className="mt-6 rounded-[1.5rem] border border-slate-900 bg-slate-950 px-5 py-5 text-white shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-200">
            Most fragile now
          </p>
          <div className="mt-3 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-2xl">
              <p className="text-2xl font-semibold tracking-tight">
                {primaryFragile.lead_name}
              </p>
              <p className="mt-1 text-sm text-slate-300">
                {primaryFragile.company_name}
              </p>
              <p className="mt-4 text-sm leading-6 text-slate-200">
                {primaryFragile.relationship_reconnect_why_now ||
                  primaryFragile.relationship_timing_nudge ||
                  primaryFragile.next_step}
              </p>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <TimelineTileDark
                  label="Latest saved moment"
                  value={getLeadCardStory(primaryFragile)}
                />
                <TimelineTileDark
                  label="Best re-entry"
                  value={
                    primaryFragile.recent_email_threads.some(
                      (thread) => thread.needs_reply,
                    )
                      ? buildThreadReplyAngle(
                          getReplyThread(primaryFragile) ??
                            getNewestThread(primaryFragile)!,
                        )
                      : primaryFragile.relationship_reconnect_next_move ||
                        primaryFragile.next_step
                  }
                />
              </div>
            </div>
            <div className="flex flex-wrap gap-2 lg:justify-end">
              <Button
                type="button"
                onClick={() => onSelectLead(primaryFragile.id)}
                className="border border-white/20 bg-white text-slate-950 hover:bg-slate-100"
              >
                Open relationship
              </Button>
              {primaryFragile.recent_email_threads.some(
                (thread) => thread.needs_reply,
              ) ? (
                <Button
                  type="button"
                  variant="outline"
                  className="border-white/20 bg-transparent text-white hover:bg-white/10 hover:text-white"
                  onClick={() =>
                    onRunAction(primaryFragile.id, "/clientos/follow-ups", {
                      objective: "follow_up",
                      tone: "warm",
                      length: "short",
                      status: "Drafting a reply from Attention...",
                    })
                  }
                >
                  Draft reply
                </Button>
              ) : null}
              {isReconnectMoment(primaryFragile) ? (
                <Button
                  type="button"
                  variant="outline"
                  className="border-white/20 bg-transparent text-white hover:bg-white/10 hover:text-white"
                  onClick={() =>
                    onRunAction(primaryFragile.id, "/clientos/follow-ups", {
                      objective: "revive",
                      tone: "warm",
                      length: "short",
                      status: "Drafting a reconnect from Attention...",
                    })
                  }
                >
                  Draft reconnect
                </Button>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}

      {needsCareFirst.length ? (
        <div className="mt-6 rounded-[1.5rem] border bg-slate-50/80 p-4">
          <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                Protect first
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                Start here if you want the shortest path to protecting a warm
                relationship before it fully slips.
              </p>
            </div>
            <p className="text-xs text-slate-500">
              Reply pressure and quiet relationships surface before older
              category lanes
              do.
            </p>
          </div>
          <div className="mt-4 grid gap-3 xl:grid-cols-2">
            {needsCareFirst.map((item) => {
              const selected = item.id === selectedLeadId;
              const reconnectable = isReconnectMoment(item);
              const replyThread = getReplyThread(item);
              const latestThread = getNewestThread(item);
              return (
                <div
                  key={`${item.id}-needs-care`}
                  className={`rounded-[1.2rem] border px-4 py-4 text-left transition ${
                    selected
                      ? "border-slate-900 bg-white shadow-sm"
                      : "border-slate-200 bg-white/90 hover:border-slate-400"
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => onSelectLead(item.id)}
                    className="block w-full text-left"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-slate-950">
                          {item.lead_name}
                        </p>
                        <p className="mt-1 text-xs text-slate-500">
                          {item.company_name}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {item.relationship_state === "stale" ? (
                          <MiniFlag tone="warning" label="Stale" />
                        ) : null}
                        {item.relationship_state === "drifting" ? (
                          <MiniFlag tone="warning" label="Drifting" />
                        ) : null}
                        {item.relationship_state === "at_risk" ? (
                          <MiniFlag tone="critical" label="At risk" />
                        ) : null}
                        {item.recent_email_threads.some(
                          (thread) => thread.needs_reply,
                        ) ? (
                          <MiniFlag tone="critical" label="Reply" />
                        ) : null}
                      </div>
                    </div>
                    <p className="mt-3 text-sm leading-6 text-slate-700">
                      {item.relationship_reconnect_why_now ||
                        item.relationship_timing_nudge ||
                        item.next_step}
                    </p>
                    <div className="mt-3 grid gap-3 md:grid-cols-2">
                      <TimelineTile
                        label="Latest saved moment"
                        value={getLeadCardStory(item)}
                      />
                      <TimelineTile
                        label={
                          item.recent_email_threads.some(
                            (thread) => thread.needs_reply,
                          )
                            ? "Reply angle"
                            : "Open loop"
                        }
                        value={
                          item.recent_email_threads.some(
                            (thread) => thread.needs_reply,
                          )
                            ? buildThreadReplyAngle(
                                replyThread ?? latestThread ?? getNewestThread(item)!,
                              )
                            : item.relationship_reconnect_next_move ||
                              (hasOpenLoop(item)
                                ? latestThread?.open_loop ||
                                  latestThread?.unresolved_hint ||
                                  item.next_step
                                : item.next_step)
                        }
                      />
                    </div>
                    {reconnectable ? (
                      <div className="mt-3 rounded-xl border bg-slate-50 px-3 py-3">
                        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">
                          Best re-entry
                        </p>
                        <p className="mt-2 text-sm leading-6 text-slate-700">
                          {item.relationship_reconnect_next_move ||
                            item.next_step}
                        </p>
                        <p className="mt-3 text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">
                          Why it can still land
                        </p>
                        <p className="mt-2 text-sm leading-6 text-slate-700">
                          {describeReconnectWindow(item)}
                        </p>
                        <p className="mt-3 text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">
                          Starter line
                        </p>
                        <p className="mt-2 text-sm leading-6 text-slate-700">
                          {buildReconnectStarterLine(item)}
                        </p>
                        <p className="mt-3 text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">
                          If it stays quiet
                        </p>
                        <p className="mt-2 text-sm leading-6 text-slate-700">
                          {buildReconnectFallbackStep(item)}
                        </p>
                      </div>
                    ) : null}
                    <p className="mt-3 text-xs text-slate-500">
                      {formatDateTime(item.last_meaningful_interaction_at)} ·{" "}
                      {formatRelationshipState(item.relationship_state)}
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
                    {item.recent_email_threads.some(
                      (thread) => thread.needs_reply,
                    ) ? (
                      <button
                        type="button"
                        onClick={() =>
                          onRunAction(item.id, "/clientos/follow-ups", {
                            objective: "follow_up",
                            tone: "warm",
                            length: "short",
                            status: "Drafting a reply from Attention...",
                          })
                        }
                        className="rounded-full border border-slate-300 bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-slate-700 transition hover:border-slate-500 hover:text-slate-950"
                      >
                        Draft reply
                      </button>
                    ) : null}
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
          const stageItems = [...(itemsByStage.get(stage.stage) ?? [])].sort(
            (left, right) => compareAttentionPriority(left, right),
          );
          const stageLabel = formatStageLabel(stage.stage);
          const urgentStageItems = stageItems.filter(
            (item) =>
              item.recent_email_threads.some((thread) => thread.needs_reply) ||
              relationshipStateUrgency(item.relationship_state) > 0,
          ).length;
          return (
            <section
              key={stage.stage}
              className="min-w-[280px] flex-1 rounded-[1.5rem] border bg-slate-50/80 p-4"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                    Relationship group
                  </p>
                  <h3 className="mt-2 text-xl font-semibold tracking-tight text-slate-950">
                    {stageLabel}
                  </h3>
                  <p className="mt-2 text-sm leading-6 text-slate-600">
                    {urgentStageItems
                      ? `${urgentStageItems} relationship${urgentStageItems === 1 ? "" : "s"} here still need a warmer move.`
                      : "Nothing here feels especially fragile right now."}
                  </p>
                </div>
                <div className="rounded-full border border-slate-200 bg-white px-3 py-1 text-sm font-semibold text-slate-700">
                  {stage.lead_count}
                </div>
              </div>

              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                <TimelineTile
                  label="Needs care now"
                  value={String(stage.overdue_count)}
                />
                <TimelineTile
                  label="Coming up soon"
                  value={String(stage.due_this_week_count)}
                />
                <TimelineTile
                  label="Warm openings"
                  value={String(stage.high_priority_count)}
                />
                <TimelineTile
                  label="Quiet here"
                  value={String(stage.dormant_count)}
                />
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
                          <p className="text-sm font-semibold text-slate-950">
                            {item.lead_name}
                          </p>
                          <p className="mt-1 text-xs text-slate-500">
                            {item.company_name} · {item.contact_channel}
                          </p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {item.relationship_state === "stale" ? (
                            <MiniFlag tone="warning" label="Stale" />
                          ) : null}
                          {item.relationship_state === "drifting" ? (
                            <MiniFlag tone="warning" label="Drifting" />
                          ) : null}
                          {item.relationship_state === "at_risk" ? (
                            <MiniFlag tone="critical" label="At risk" />
                          ) : null}
                          <PriorityBadge priority={item.priority} />
                        </div>
                      </div>
                      <p className="mt-3 text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">
                        Latest saved moment
                      </p>
                      <p className="mt-1 text-sm leading-6 text-slate-700">
                        {getLeadCardStory(item)}
                      </p>
                      <p className="mt-3 text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">
                        Why now
                      </p>
                      <p className="mt-1 text-sm leading-6 text-slate-600">
                        {getLeadCardWhyNow(item)}
                      </p>
                      <p className="mt-3 text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">
                        Next move
                      </p>
                      <p className="mt-1 text-sm leading-6 text-slate-600">
                        {isReconnectMoment(item)
                          ? item.relationship_reconnect_next_move ||
                            item.next_step
                          : item.next_step}
                      </p>
                      {isReconnectMoment(item) ? (
                        <p className="mt-3 text-sm leading-6 text-slate-600">
                          {buildReconnectStarterLine(item)}
                        </p>
                      ) : null}
                      <p className="mt-3 text-xs text-slate-500">
                        {formatDateTime(item.next_follow_up_at)}
                      </p>
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
  inboxSummary,
  selectedLeadId,
  onSelectLead,
  onDraftAction,
  inboxQuery,
  inboxFilter,
  onInboxQueryChange,
  onInboxFilterChange,
  effectiveInboxQuery,
}: {
  items: CRMLeadFollowUp[];
  inboxSummary: CRMFollowUpOverview["inbox_summary"];
  selectedLeadId: string | null;
  onSelectLead: (leadId: string, threadId?: string | null) => void;
  onDraftAction: (
    leadId: string,
    draft: {
      objective: CRMEmailDraft["objective"];
      tone: CRMEmailDraft["tone"];
      length: CRMEmailDraft["length"];
      status: string;
    },
    threadId?: string | null,
  ) => void;
  inboxQuery: string;
  inboxFilter: InboxFilter;
  onInboxQueryChange: (value: string) => void;
  onInboxFilterChange: (value: InboxFilter) => void;
  effectiveInboxQuery: string;
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
    .sort(
      (left, right) =>
        new Date(right.thread.last_message_at).getTime() -
        new Date(left.thread.last_message_at).getTime(),
    );
  const filteredThreads = threads.filter((item) =>
    matchesInboxThread(item, effectiveInboxQuery, inboxFilter),
  );
  const autoCreatedCount = inboxSummary?.auto_created_contact_count ?? 0;
  const needsReplyCount =
    inboxSummary?.needs_reply_count ??
    filteredThreads.filter(({ thread }) => thread.needs_reply).length;
  const openLoopCount = filteredThreads.filter(({ thread }) =>
    isUnresolvedThread(thread),
  ).length;
  const quietCount =
    inboxSummary?.stale_thread_count ??
    filteredThreads.filter(({ thread }) => isQuietThread(thread)).length;
  const inboxCreatedRelationships = items
    .filter((item) => isInboxCreatedRelationship(item))
    .sort(
      (left, right) => getNewestThreadTimestamp(right) - getNewestThreadTimestamp(left),
    );
  const urgentThreads = filteredThreads.filter(
    ({ thread }) =>
      thread.needs_reply ||
      thread.waiting_on_contact ||
      isQuietThread(thread) ||
      isUnresolvedThread(thread),
  );
  const steadyThreads = filteredThreads.filter(
    ({ thread }) =>
      !(
        thread.needs_reply ||
        thread.waiting_on_contact ||
        isQuietThread(thread) ||
        isUnresolvedThread(thread)
      ),
  );
  const primaryUrgentThread = urgentThreads[0] ?? null;

  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
        Inbox continuity
      </p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">
        Recent conversations Brivoly is quietly holding together.
      </h2>
      <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
        Let email stay the default relationship memory source. Brivoly keeps the
        live thread, the latest change, and the cleanest next move close enough
        that you rarely need to reconstruct the story by hand.
      </p>
      <div className="mt-5 grid gap-3 xl:grid-cols-4">
        <CompactMetricLight
          label="Reply soon"
          value={
            needsReplyCount
              ? `${needsReplyCount} thread${needsReplyCount === 1 ? "" : "s"}`
              : "Clear"
          }
          tone={needsReplyCount ? "critical" : "neutral"}
        />
        <CompactMetricLight
          label="Open loops"
          value={
            openLoopCount
              ? `${openLoopCount} thread${openLoopCount === 1 ? "" : "s"}`
              : "Clear"
          }
          tone={openLoopCount ? "warning" : "neutral"}
        />
        <CompactMetricLight
          label="Quiet threads"
          value={
            quietCount
              ? `${quietCount} thread${quietCount === 1 ? "" : "s"}`
              : "Quiet"
          }
          tone={quietCount ? "warning" : "neutral"}
        />
        <CompactMetricLight
          label="Brought in from email"
          value={
            autoCreatedCount
              ? `${autoCreatedCount} relationship${autoCreatedCount === 1 ? "" : "s"}`
              : "Waiting"
          }
          tone={autoCreatedCount ? "positive" : "neutral"}
        />
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => onInboxFilterChange("reply")}
          className="rounded-full border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-700 transition hover:border-slate-400 hover:bg-white hover:text-slate-950"
        >
          Start with replies
        </button>
        <button
          type="button"
          onClick={() => onInboxFilterChange("waiting")}
          className="rounded-full border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-700 transition hover:border-slate-400 hover:bg-white hover:text-slate-950"
        >
          Focus waiting threads
        </button>
        <button
          type="button"
          onClick={() => onInboxFilterChange("unresolved")}
          className="rounded-full border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-700 transition hover:border-slate-400 hover:bg-white hover:text-slate-950"
        >
          Focus open loops
        </button>
        <button
          type="button"
          onClick={() => onInboxFilterChange("long_thread")}
          className="rounded-full border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-700 transition hover:border-slate-400 hover:bg-white hover:text-slate-950"
        >
          Focus long threads
        </button>
        <button
          type="button"
          onClick={() => onInboxFilterChange("new_from_inbox")}
          className="rounded-full border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-700 transition hover:border-slate-400 hover:bg-white hover:text-slate-950"
        >
          Focus new from email
        </button>
      </div>
      <div className="mt-5 rounded-[1.35rem] border bg-slate-50/80 p-4">
        <div className="grid gap-3 lg:grid-cols-[1.2fr_auto] lg:items-center">
          <div className="flex flex-col gap-3 sm:flex-row">
            <input
              value={inboxQuery}
              onChange={(event) => onInboxQueryChange(event.target.value)}
              placeholder="Search by name, company, subject, email, or open loop"
              className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400"
            />
            {(inboxQuery || inboxFilter !== "all") && (
              <button
                type="button"
                onClick={() => {
                  onInboxQueryChange("");
                  onInboxFilterChange("all");
                }}
                className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-700 transition hover:border-slate-400 hover:text-slate-950"
              >
                Clear view
              </button>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {[
              { value: "all", label: "All" },
              { value: "reply", label: "Reply soon" },
              { value: "waiting", label: "Waiting" },
              { value: "quiet", label: "Quiet" },
              { value: "unresolved", label: "Open loop" },
              { value: "long_thread", label: "Long thread" },
              { value: "new_from_inbox", label: "New from email" },
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
      {primaryUrgentThread ? (
        <div className="mt-6 rounded-[1.5rem] border border-slate-900 bg-slate-950 px-5 py-5 text-white shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-200">
            Start here
          </p>
          <div className="mt-3 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-2xl">
              <p className="text-2xl font-semibold tracking-tight">
                {primaryUrgentThread.leadName}
              </p>
              <p className="mt-1 text-sm text-slate-300">
                {primaryUrgentThread.companyName}
              </p>
              <p className="mt-3 text-sm leading-6 text-slate-200">
                {primaryUrgentThread.thread.relationship_pulse}
              </p>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <TimelineTileDark
                  label="One read"
                  value={buildThreadOneRead(primaryUrgentThread.thread)}
                />
                <TimelineTileDark
                  label="Reply angle"
                  value={buildThreadReplyAngle(primaryUrgentThread.thread)}
                />
              </div>
            </div>
            <div className="flex flex-wrap gap-2 lg:justify-end">
              <Button
                type="button"
                onClick={() =>
                  onDraftAction(
                    primaryUrgentThread.leadId,
                    primaryUrgentThread.thread.needs_reply
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
                    primaryUrgentThread.thread.thread_id,
                  )
                }
                className="border border-white/20 bg-white text-slate-950 hover:bg-slate-100"
              >
                {primaryUrgentThread.thread.needs_reply
                  ? "Draft reply"
                  : "Draft reconnect"}
              </Button>
              <Button
                type="button"
                variant="outline"
                className="border-white/20 bg-transparent text-white hover:bg-white/10 hover:text-white"
                onClick={() =>
                  onSelectLead(
                    primaryUrgentThread.leadId,
                    primaryUrgentThread.thread.thread_id,
                  )
                }
              >
                Open relationship
              </Button>
            </div>
          </div>
        </div>
      ) : null}
      {inboxCreatedRelationships.length ? (
        <div className="mt-6 rounded-[1.5rem] border bg-sky-50/60 p-4">
          <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-700">
                New from email
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                These relationships were pulled into Client OS from live inbox
                activity, so you can turn a real thread into relationship
                memory without re-entering the basics.
              </p>
            </div>
            <p className="text-xs text-slate-500">
              {inboxCreatedRelationships.length} relationship
              {inboxCreatedRelationships.length === 1 ? "" : "s"}
            </p>
          </div>
          <div className="mt-4 grid gap-3 xl:grid-cols-2">
            {inboxCreatedRelationships.slice(0, 4).map((lead) => {
              const newestThread = getNewestThread(lead);
              return (
                <div
                  key={`${lead.id}-inbox-born`}
                  className="rounded-[1.2rem] border bg-white px-4 py-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-slate-950">
                        {lead.lead_name}
                      </p>
                      <p className="mt-1 text-xs text-slate-500">
                        {lead.company_name || lead.email_address || "Inbox relationship"}
                      </p>
                    </div>
                    <MiniFlag tone="neutral" label="Inbox-created" />
                  </div>
                  <div className="mt-3 grid gap-3 md:grid-cols-2">
                    <TimelineTile
                      label="Latest thread"
                      value={
                        newestThread
                          ? `${newestThread.subject} · ${formatDateTime(newestThread.last_message_at)}`
                          : "No synced thread yet."
                      }
                    />
                    <TimelineTile
                      label="Why it matters now"
                      value={getLeadCardWhyNow(lead)}
                    />
                    <TimelineTile
                      label="Best next move"
                      value={
                        newestThread
                          ? newestThread.next_touch_hint || newestThread.open_loop || lead.next_step
                          : lead.next_step
                      }
                    />
                    <TimelineTile
                      label="Latest saved moment"
                      value={getLeadCardStory(lead)}
                    />
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => onSelectLead(lead.id, newestThread?.thread_id)}
                    >
                      Open relationship
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() =>
                        onDraftAction(
                          lead.id,
                          newestThread?.needs_reply
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
                                status: "Drafting a first note from inbox-created relationship...",
                              },
                          newestThread?.thread_id,
                        )
                      }
                    >
                      {newestThread?.needs_reply ? "Draft reply" : "Draft first note"}
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
      <div className="mt-6 space-y-6">
        {urgentThreads.length ? (
          <div>
            <div className="flex items-end justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                  Needs you now
                </p>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  These threads are waiting on you, carrying an open loop,
                  starting to drift, or worth reopening before the relationship
                  loses warmth.
                </p>
              </div>
              <p className="text-xs text-slate-500">
                {urgentThreads.length} conversation
                {urgentThreads.length === 1 ? "" : "s"}
              </p>
            </div>
            <div className="mt-4 space-y-4">
              {urgentThreads.map((item) => (
                <InboxThreadCard
                  key={item.thread.thread_id}
                  item={item}
                  selected={item.leadId === selectedLeadId}
                  onSelectLead={onSelectLead}
                  onDraftAction={onDraftAction}
                />
              ))}
            </div>
          </div>
        ) : null}
        {steadyThreads.length ? (
          <div>
            <div className="flex items-end justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                  Still warm
                </p>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  Brivoly is holding onto the context here so you can step back
                  in without rereading the whole thread.
                </p>
              </div>
              <p className="text-xs text-slate-500">
                {steadyThreads.length} conversation
                {steadyThreads.length === 1 ? "" : "s"}
              </p>
            </div>
            <div className="mt-4 space-y-4">
              {steadyThreads.map((item) => (
                <InboxThreadCard
                  key={item.thread.thread_id}
                  item={item}
                  selected={item.leadId === selectedLeadId}
                  onSelectLead={onSelectLead}
                  onDraftAction={onDraftAction}
                />
              ))}
            </div>
          </div>
        ) : null}
        {!filteredThreads.length ? (
          <div className="rounded-[1.35rem] border border-dashed bg-slate-50/70 p-6 text-sm leading-6 text-slate-600">
            <p>
              No conversations match this view yet. Once inbox sync is flowing,
              this becomes the quiet memory layer for who said what and who
              needs a reply.
            </p>
            {(inboxQuery || inboxFilter !== "all") && (
              <div className="mt-4">
                <button
                  type="button"
                  onClick={() => {
                    onInboxQueryChange("");
                    onInboxFilterChange("all");
                  }}
                  className="rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-700 transition hover:border-slate-400 hover:text-slate-950"
                >
                  Reset inbox view
                </button>
              </div>
            )}
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
  onSelectLead: (leadId: string, threadId?: string | null) => void;
  onDraftAction: (
    leadId: string,
    draft: {
      objective: CRMEmailDraft["objective"];
      tone: CRMEmailDraft["tone"];
      length: CRMEmailDraft["length"];
      status: string;
    },
    threadId?: string | null,
  ) => void;
}) {
  const { leadId, leadName, companyName, stage, thread } = item;
  const oneRead = buildThreadOneRead(thread);
  const replyAngle = buildThreadReplyAngle(thread);
  const latestStory = thread.recent_change_hint || thread.continuity_memory;

  return (
    <div
      className={`block w-full rounded-[1.35rem] border px-5 py-5 text-left transition ${
        selected
          ? "border-slate-900 bg-white shadow-sm"
          : "bg-slate-50/80 hover:border-slate-400 hover:bg-white"
      }`}
    >
      <button
        type="button"
        onClick={() => onSelectLead(leadId, thread.thread_id)}
        className="block w-full text-left"
      >
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
              {thread.needs_reply ? "Reply pressure" : "Thread continuity"} ·{" "}
              {thread.last_message_direction === "inbound"
                ? "Needs your reply"
                : "Waiting on them"}
            </p>
            <h3 className="mt-2 text-xl font-semibold tracking-tight text-slate-950">
              {thread.subject}
            </h3>
            <p className="mt-1 text-sm text-slate-600">
              {leadName} · {companyName}
            </p>
            <p className="mt-3 text-sm font-medium text-slate-900">
              {thread.relationship_pulse}
            </p>
            <div className="mt-3 rounded-[1rem] border bg-white px-4 py-3">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                One read
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-700">
                {oneRead}
              </p>
            </div>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              {thread.continuity_span}
            </p>
            {thread.carry_forward_hint ? (
              <p className="mt-3 text-sm leading-6 text-slate-700">
                {thread.carry_forward_hint}
              </p>
            ) : null}
            {thread.unresolved_hint ? (
              <p className="mt-3 text-sm leading-6 text-slate-700">
                {thread.unresolved_hint}
              </p>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {thread.needs_reply ? (
              <MiniFlag tone="critical" label="Reply" />
            ) : null}
            {thread.waiting_on_contact ? (
              <MiniFlag tone="warning" label="Waiting" />
            ) : null}
            {isQuietThread(thread) ? (
              <MiniFlag tone="neutral" label="Quiet" />
            ) : null}
            {isUnresolvedThread(thread) ? (
              <MiniFlag tone="warning" label="Open loop" />
            ) : null}
            {isLongThread(thread) ? (
              <MiniFlag tone="neutral" label="Long thread" />
            ) : null}
            <div className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-slate-600">
              {thread.message_count} msg
            </div>
          </div>
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <TimelineTile label="Brivoly read" value={thread.next_touch_hint} />
          <TimelineTile
            label="Latest saved moment"
            value={latestStory || thread.memory_summary}
          />
          <TimelineTile label="Reply angle" value={replyAngle} />
          <TimelineTile label="Open loop" value={thread.open_loop} />
          <TimelineTile
            label="What changed"
            value={thread.recent_change_hint}
          />
          <TimelineTile
            label="Last turn"
            value={formatDateTime(thread.last_message_at)}
          />
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
              thread.thread_id,
            );
          }}
        >
          {thread.needs_reply ? "Draft reply" : "Draft reconnect"}
        </Button>
        {isUnresolvedThread(thread) ? (
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              onDraftAction(
                leadId,
                {
                  objective: "close_loop",
                  tone: "direct",
                  length: "short",
                  status: "Drafting a close-the-loop note from Inbox...",
                },
                thread.thread_id,
              );
            }}
          >
            Close loop
          </Button>
        ) : null}
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            onSelectLead(leadId, thread.thread_id);
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
  onDraftAction: (
    draft: {
      objective: CRMEmailDraft["objective"];
      tone: CRMEmailDraft["tone"];
      length: CRMEmailDraft["length"];
      status: string;
    },
    threadId?: string | null,
  ) => void;
  isDrafting: boolean;
  draftStatus: string | null;
}) {
  const latestThread = getNewestThread(lead);
  const quietReconnect = latestThread
    ? isQuietThread(latestThread) && !latestThread.needs_reply
    : false;
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
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
        Next move
      </p>
      <h3 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
        {lead.lead_name}
      </h3>
      <p className="mt-1 text-sm text-slate-600">{lead.company_name}</p>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <TimelineTile
          label="Brivoly read"
          value={
            latestThread ? latestThread.next_touch_hint : "No synced thread yet"
          }
        />
        <TimelineTile
          label="Recommended next touch"
          value={
            lead.relationship_upload_follow_through_hint ||
            (shouldReconnect
              ? lead.relationship_reconnect_next_move || lead.next_step
              : lead.next_step)
          }
        />
        <TimelineTile
          label="Reply angle"
          value={
            latestThread
              ? buildThreadReplyAngle(latestThread)
              : lead.relationship_reconnect_next_move || lead.next_step
          }
        />
      </div>
      {latestThread ? (
        <div className="mt-4 rounded-[1.2rem] border bg-slate-50/80 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
            Latest thread
          </p>
          <p className="mt-2 text-sm font-medium text-slate-900">
            {latestThread.subject}
          </p>
          <p className="mt-2 text-sm font-medium text-slate-900">
            {latestThread.relationship_pulse}
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-700">
            {buildThreadOneRead(latestThread)}
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            {latestThread.continuity_span}
          </p>
        </div>
      ) : null}
      {latestThread?.continuity_memory ||
      latestThread?.recent_change_hint ||
      latestThread?.carry_forward_hint ||
      latestThread?.open_loop ? (
        <div className="mt-4 rounded-[1.2rem] border bg-slate-50/80 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
            Conversation memory
          </p>
          {latestThread?.continuity_memory ? (
            <p className="mt-2 text-sm leading-6 text-slate-600">
              {latestThread.continuity_memory}
            </p>
          ) : null}
          {latestThread?.recent_change_hint ? (
            <p className="mt-2 text-sm leading-6 text-slate-600">
              {latestThread.recent_change_hint}
            </p>
          ) : null}
          {latestThread?.carry_forward_hint ? (
            <p className="mt-2 text-sm leading-6 text-slate-700">
              {latestThread.carry_forward_hint}
            </p>
          ) : null}
          {latestThread?.open_loop ? (
            <div className="mt-3 rounded-2xl border bg-white px-4 py-3">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                Open loop
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-700">
                {latestThread.open_loop}
              </p>
            </div>
          ) : null}
        </div>
      ) : null}
      {latestThread?.unresolved_hint ? (
        <div className="mt-4 rounded-[1.2rem] border bg-slate-50/80 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
            Still unresolved
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            {latestThread.unresolved_hint}
          </p>
        </div>
      ) : null}
      {lead.relationship_recent_upload_summary ? (
        <div className="mt-4 rounded-[1.2rem] border bg-slate-50/80 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
            Fresh client context
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            {lead.relationship_recent_upload_summary}
          </p>
          {lead.relationship_upload_follow_through_hint ? (
            <p className="mt-3 text-sm leading-6 text-slate-700">
              {lead.relationship_upload_follow_through_hint}
            </p>
          ) : null}
          {lead.relationship_meeting_prep_summary ? (
            <div className="mt-3 rounded-2xl border bg-white px-4 py-3">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                Use it in the next touch
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-700">
                {lead.relationship_meeting_prep_summary}
              </p>
            </div>
          ) : null}
          <div className="mt-4 flex flex-wrap gap-3">
            <Button
              type="button"
              variant="outline"
              disabled={isDrafting}
              onClick={() =>
                onDraftAction(
                  {
                    objective: shouldReconnect ? "revive" : "follow_up",
                    tone: "warm",
                    length: "short",
                    status: shouldReconnect
                      ? "Drafting a reconnect from fresh client context..."
                      : "Drafting a reply from fresh client context...",
                  },
                  latestThread?.thread_id ?? null,
                )
              }
            >
              {shouldReconnect
                ? "Turn this into a reconnect"
                : "Turn this into a note"}
            </Button>
          </div>
        </div>
      ) : null}
      {shouldReconnect ? (
        <div className="mt-4 rounded-[1.2rem] border bg-slate-50/80 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
            Gentle re-entry
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            {lead.relationship_reconnect_why_now ||
              lead.relationship_timing_nudge}
          </p>
          {lead.relationship_reconnect_next_move ? (
            <div className="mt-3 rounded-2xl border bg-white px-4 py-3">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                Next move
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-700">
                {lead.relationship_reconnect_next_move}
              </p>
            </div>
          ) : null}
          <p className="mt-3 text-sm leading-6 text-slate-700">
            {lead.relationship_reconnect_message_hint ||
              "Keep it warm, brief, and easy to answer."}
          </p>
        </div>
      ) : null}
      <div className="mt-4 flex flex-wrap gap-3">
        <Button
          disabled={isDrafting}
          onClick={() =>
            onDraftAction(primaryAction.draft, latestThread?.thread_id ?? null)
          }
        >
          {isDrafting ? "Drafting..." : primaryAction.label}
        </Button>
        <Button asChild variant="outline">
          <Link href="/clientos/follow-ups">Open relationship</Link>
        </Button>
      </div>
      {draftStatus ? (
        <p className="mt-4 text-sm text-slate-500">{draftStatus}</p>
      ) : null}
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
    ? `Whenever you want to send a quick update, screenshot, or note, just use this page: ${shareLink}`
    : "";
  const shareTextMessage = shareLink
    ? `Quickest path: open this link on your phone and send the screenshot or note there. ${shareLink}`
    : "";

  async function copyText(value: string, successMessage: string) {
    if (!value) {
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
      setShareStatus(successMessage);
    } catch {
      setShareStatus(
        "Copy did not work in this browser. You can still copy the link manually.",
      );
    }
  }

  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
        Client dropzone
      </p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">
        Keep one low-friction client handoff page ready.
      </h2>
      <p className="mt-3 text-sm leading-6 text-slate-600">
        Brivoly gives you one simple no-login page for screenshots, whiteboard
        photos, and note images. Set it once, then keep reusing the same quiet
        page whenever a client wants to send something over.
      </p>

      {!advancedAiUnlocked ? (
        <div className="mt-5 rounded-[1.3rem] border border-amber-200 bg-amber-50 px-4 py-4 text-sm leading-6 text-amber-900">
          Shared image capture uses the same paid AI layer as advanced
          spreadsheet and file interpretation.
        </div>
      ) : null}

      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <div className="rounded-[1.3rem] border bg-slate-50 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
            What clients can send
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-700">
            Screenshot updates, whiteboard photos, handwritten notes, or other
            quick visual context that would otherwise get lost in chat and
            email.
          </p>
        </div>
        <div className="rounded-[1.3rem] border bg-slate-50 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
            What Brivoly does next
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-700">
            Brivoly folds the update back into relationship memory so you can
            reopen the context later without hunting through email, chat, or
            uploads.
          </p>
        </div>
      </div>
      <div className="mt-5 rounded-[1.3rem] border bg-slate-50 px-4 py-4">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
          What the client experience feels like
        </p>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          {[
            {
              step: "Open",
              body: "They tap one link on their phone instead of being asked to sign in or explain where the update belongs.",
            },
            {
              step: "Send",
              body: "They drop in a screenshot, whiteboard photo, or quick note while the context is still fresh.",
            },
            {
              step: "Move on",
              body: "Brivoly folds it back into relationship memory so you can use it later without chasing the file again.",
            },
          ].map((item) => (
            <div
              key={item.step}
              className="rounded-[1rem] border bg-white px-4 py-4"
            >
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                {item.step}
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-700">
                {item.body}
              </p>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-5 rounded-[1.3rem] border bg-slate-50 px-4 py-4">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
          Ready to share
        </p>
        <p className="mt-2 text-sm font-medium text-slate-900">
          {intakeChannel?.magic_link_url
            ? "Your handoff link is ready."
            : "The handoff link is not ready yet."}
        </p>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          {intakeChannel?.instructions ??
            "Turn this on once so clients have a phone-friendly page they can keep using whenever something changes."}
        </p>
        {normalizedChannels.length ? (
          <p className="mt-3 text-sm text-slate-700">
            Usual ways clients send updates here:{" "}
            <span className="font-medium">{normalizedChannels.join(", ")}</span>
          </p>
        ) : null}
        {routingNotes ? (
          <p className="mt-2 text-sm leading-6 text-slate-600">
            {routingNotes}
          </p>
        ) : null}
        {intakeChannel?.magic_link_url ? (
          <>
            <p className="mt-4 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
              Client handoff link
            </p>
            <a
              href={intakeChannel.magic_link_url}
              target="_blank"
              rel="noreferrer"
              className="mt-2 block overflow-x-auto rounded-2xl border bg-white px-4 py-3 text-sm text-slate-900 underline decoration-slate-300 underline-offset-4"
            >
              {intakeChannel.magic_link_url}
            </a>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => copyText(shareLink, "Client link copied.")}
              >
                Copy link
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => copyText(shareMessage, "Share note copied.")}
              >
                Copy share note
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() =>
                  copyText(shareTextMessage, "Text-friendly note copied.")
                }
              >
                Copy text message
              </Button>
            </div>
            <div className="mt-4 rounded-[1rem] border bg-white px-4 py-4">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                Share note preview
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-700">
                {shareMessage ||
                  "Once the handoff link is live, Brivoly will give you a short share note you can paste into email, chat, or text."}
              </p>
              <p className="mt-3 text-xs text-slate-500">
                Keep it short. Clients should understand the next step without
                reading instructions twice.
              </p>
            </div>
            <p className="mt-3 text-xs text-slate-500">
              Share the link once, then keep reusing it. No login or extra
              account steps are required.
            </p>
            {shareStatus ? (
              <p className="mt-2 text-sm text-slate-600">{shareStatus}</p>
            ) : null}
          </>
        ) : null}
      </div>
    </section>
  );
}

function IntakeTaskNav({ activeTask }: { activeTask: CRMIntakeTask }) {
  const items: Array<{
    href: string;
    title: string;
    body: string;
    task: CRMIntakeTask;
  }> = [
    {
      href: "/clientos/intake",
      title: "Overview",
      body: "See the calm default flow at a glance.",
      task: "hub",
    },
    {
      href: "/clientos/intake/profile",
      title: "Usual formats",
      body: "Show what clients usually send over.",
      task: "profile",
    },
    {
      href: "/clientos/intake/routing",
      title: "Usual path",
      body: "Choose the easiest way in once.",
      task: "routing",
    },
    {
      href: "/clientos/intake/capture",
      title: "Share link",
      body: "Keep one phone-friendly handoff page ready.",
      task: "capture",
    },
  ];

  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-5 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
        Client dropzone
      </p>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        {items.map((item) => {
          const active = item.task === activeTask;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`rounded-[1.2rem] border px-4 py-4 transition ${
                active
                  ? "border-slate-900 bg-slate-950 text-white"
                  : "bg-slate-50/80 hover:border-slate-400 hover:bg-white"
              }`}
            >
              <p
                className={`text-xs font-semibold uppercase tracking-[0.18em] ${active ? "text-cyan-200" : "text-slate-400"}`}
              >
                {item.title}
              </p>
              <p
                className={`mt-2 text-sm leading-6 ${active ? "text-slate-100" : "text-slate-700"}`}
              >
                {item.body}
              </p>
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
        eyebrow="First"
        title="Show the kinds of updates clients usually send"
        body={
          advancedAiUnlocked
            ? "Your AI memory defaults are ready. Keep them close to what clients actually send."
            : "Turn on the paid AI layer before relying on note images and messy files to bring client context back in."
        }
      />
      <TaskSummaryCard
        href="/clientos/intake/routing"
        eyebrow="Next"
        title="Choose the easiest handoff path"
        body={
          normalizedChannels.length
            ? `Usual paths are ready: ${normalizedChannels.join(", ")}.`
            : "Set one path and one short note so sending updates feels obvious."
        }
      />
      <TaskSummaryCard
        href="/clientos/intake/capture"
        eyebrow="Then"
        title="Share the handoff link"
        body={
          hasMagicLink
            ? "A signed no-login page is live and ready to reuse with clients."
            : "Turn this on once so clients can send updates from their phone without friction."
        }
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
    <Link
      href={href}
      className="block min-w-0 overflow-hidden rounded-[1.75rem] border bg-white/90 p-6 shadow-sm transition hover:border-slate-400 hover:bg-white"
    >
      <p className="break-words text-xs font-semibold uppercase tracking-[0.18em] text-slate-400 [overflow-wrap:anywhere] sm:tracking-[0.24em]">
        {eyebrow}
      </p>
      <h3 className="mt-3 break-words text-2xl font-semibold tracking-tight text-slate-950 [overflow-wrap:anywhere]">
        {title}
      </h3>
      <p className="mt-3 break-words text-sm leading-6 text-slate-600 [overflow-wrap:anywhere]">
        {body}
      </p>
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
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
        Usual path
      </p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">
        Keep the easiest handoff path ready.
      </h2>
      <p className="mt-3 text-sm leading-6 text-slate-600">
        Keep this simple: choose the usual paths for this account and leave one
        short note so every new update lands in the right place without extra
        explaining.
      </p>

      <div className="mt-5 space-y-4">
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
            How updates usually arrive
          </span>
          <input
            value={channelsDraft}
            onChange={(event) => onChannelsDraftChange(event.target.value)}
            placeholder="magic_link, email, whatsapp"
            className="mt-2 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400 focus:bg-white"
          />
        </label>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => {
              onChannelsDraftChange("upload, magic_link, email");
              onRoutingNotesDraftChange(
                "Use the shared link for screenshots and quick updates. Use email when someone sends a longer file, thread, or fuller project context.",
              );
            }}
            className="rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-600 transition hover:border-slate-400 hover:text-slate-900"
          >
            Use recommended path
          </button>
          {[
            {
              label: "Shared link + email",
              value: "upload, magic_link, email",
            },
            {
              label: "Shared link + WhatsApp",
              value: "upload, magic_link, whatsapp",
            },
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
                "Use the shared link for screenshots and quick updates. Use email when someone sends a longer file, thread, or fuller project context.",
              )
            }
            className="rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-600 transition hover:border-slate-400 hover:text-slate-900"
          >
            Use recommended note
          </button>
        </div>
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
            Share note
          </span>
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
          {isSaving ? "Saving..." : "Save"}
        </Button>
        {saveStatus ? (
          <p className="text-sm text-slate-500">{saveStatus}</p>
        ) : null}
      </div>
      {!canPersistSettings ? (
        <p className="mt-3 text-sm text-slate-500">
          These defaults will appear once Brivoly finishes loading your account
          details.
        </p>
      ) : null}
    </section>
  );
}

function normalizeDisplayChannels(channels: string[]): string[] {
  return channels.map((channel) =>
    channel === "telegram" ? "magic_link" : channel,
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
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
            Usual client formats
          </p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">
            Show Brivoly what clients usually send.
          </h2>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            Keep a short memory cue and your usual source formats here so future
            spreadsheet, file, and image interpretation stays close to how you
            actually work.
          </p>
        </div>
        <div
          className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] ${advancedAiUnlocked ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-amber-200 bg-amber-50 text-amber-800"}`}
        >
          {advancedAiUnlocked
            ? "Advanced AI unlocked"
            : "Advanced AI locked"}
        </div>
      </div>

      {!advancedAiUnlocked ? (
        <div className="mt-5 rounded-[1.3rem] border border-amber-200 bg-amber-50 px-4 py-4 text-sm leading-6 text-amber-900">
          AI-assisted file, spreadsheet, and image interpretation stays behind a
          paid plan for now. Current billing status:{" "}
          {formatBillingStatusLabel(billingStatus)}.
        </div>
      ) : null}

      <div className="mt-5 space-y-4">
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
            Usual formats
          </span>
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
              onAiFormatsDraftChange(
                "csv, google_sheets, spreadsheet_screenshot",
              );
              onAiPromptDraftChange(
                "Treat uploads and messy files as relationship context first. Pull out what changed, what matters now, and the clearest next touch without adding admin work.",
              );
            }}
            className="rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-600 transition hover:border-slate-400 hover:text-slate-900"
          >
            Use recommended formats
          </button>
          {[
            {
              label: "Sheets + screenshots",
              value: "csv, google_sheets, spreadsheet_screenshot",
            },
            {
              label: "Image-first",
              value:
                "spreadsheet_screenshot, whiteboard_photo, handwritten_note",
            },
            {
              label: "Files + screenshots",
              value: "csv, google_sheets, pdf_export, spreadsheet_screenshot",
            },
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
          <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
            What to notice
          </span>
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
          {isSaving ? "Saving..." : "Save"}
        </Button>
        {saveStatus ? (
          <p className="text-sm text-slate-500">{saveStatus}</p>
        ) : null}
      </div>
      {!canPersistSettings ? (
        <p className="mt-3 text-sm text-slate-500">
          These defaults will appear once Brivoly finishes loading account
          settings.
        </p>
      ) : null}
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
  onRowOverrideChange: (
    rowNumber: number,
    fieldName: string,
    value: string,
  ) => void;
  onApplyRowFix: (rowNumber: number) => void;
}) {
  if (!preview) {
    return (
      <section className="rounded-[1.4rem] border border-dashed bg-slate-50/70 p-6">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
          Preview
        </p>
        <h3 className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">
          Nothing staged yet.
        </h3>
        <p className="mt-3 text-sm leading-6 text-slate-600">
          Check the source first to see the cleaned-up rows, duplicates, and
          anything Brivoly still needs before bringing it into memory.
        </p>
      </section>
    );
  }

  const clarificationQuestions = preview.clarification?.questions ?? [];
  const nextClarificationQuestion =
    clarificationQuestions.find(
      (question) => !clarificationAnswers[question.id],
    ) ??
    clarificationQuestions[0] ??
    null;
  const answeredClarificationCount = clarificationQuestions.filter((question) =>
    Boolean(clarificationAnswers[question.id]),
  ).length;

  return (
    <section className="rounded-[1.4rem] border bg-slate-950 p-6 text-slate-50 shadow-[0_24px_80px_-55px_rgba(15,23,42,0.9)]">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-300">
        Preview
      </p>
      <h3 className="mt-3 text-2xl font-semibold tracking-tight">
        {preview.source_label} memory check
      </h3>
      <div className="mt-5 grid gap-3 md:grid-cols-2">
        <CompactMetric label="Rows" value={String(preview.total_rows)} />
        <CompactMetric
          label="Importable"
          value={String(preview.importable_rows)}
        />
        <CompactMetric
          label="Skipped"
          value={String(preview.duplicate_rows + preview.invalid_rows)}
        />
      </div>
      {preview.clarification ? (
        <section
          className={`mt-5 rounded-[1.2rem] border p-4 ${preview.clarification.required ? "border-cyan-300/40 bg-cyan-400/10" : "border-white/10 bg-white/5"}`}
        >
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-200">
            AI clarification
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-200">
            {preview.clarification.assistant_message}
          </p>
          {preview.clarification.required ? (
            <p className="mt-2 text-xs text-cyan-100/80">
              Brivoly will walk through the remaining ambiguity one question at
              a time and re-check the sheet after each answer.
            </p>
          ) : null}
          {nextClarificationQuestion ? (
            <div className="mt-4 space-y-4">
              {clarificationQuestions.length > 1 ? (
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-100/80">
                  Question{" "}
                  {Math.min(
                    answeredClarificationCount + 1,
                    clarificationQuestions.length,
                  )}{" "}
                  of {clarificationQuestions.length}
                </p>
              ) : null}
              <ClarificationQuestionCard
                question={nextClarificationQuestion}
                selectedValue={
                  clarificationAnswers[nextClarificationQuestion.id] ?? ""
                }
                onAnswer={onClarificationAnswer}
              />
              {answeredClarificationCount > 0 ? (
                <div className="rounded-xl border border-white/10 bg-slate-900/30 px-3 py-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                    Already clarified
                  </p>
                  <div className="mt-2 space-y-2">
                    {clarificationQuestions
                      .filter((question) =>
                        Boolean(clarificationAnswers[question.id]),
                      )
                      .map((question) => {
                        const answeredChoice = question.choices.find(
                          (choice) =>
                            choice.value === clarificationAnswers[question.id],
                        );
                        return (
                          <p
                            key={question.id}
                            className="text-sm text-slate-300"
                          >
                            <span className="font-medium text-white">
                              {question.prompt}
                            </span>
                            {" · "}
                            {answeredChoice?.label ??
                              clarificationAnswers[question.id]}
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
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
              Column mapping
            </p>
            <p className="mt-2 text-sm leading-6 text-slate-300">
              Keep the suggested mapping if it looks right, or correct anything
              here before bringing it in.
            </p>
          </div>
          {isImportMappingDirty ? (
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-300">
              Needs refreshed preview
            </p>
          ) : null}
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
      {preview.rows.length > 5 ? (
        <p className="mt-3 text-xs text-slate-400">
          Showing the first 5 preview rows.
        </p>
      ) : null}
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
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
          Sheet column
        </p>
        <p className="mt-1 text-sm font-medium text-white">
          {item.original_header}
        </p>
        <p className="mt-2 text-xs text-slate-400">
          Suggested:{" "}
          {item.suggested_field
            ? formatImportFieldLabel(item.suggested_field)
            : "Leave this out"}
        </p>
      </div>
      <label className="block">
        <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
          Map to
        </span>
        <select
          value={selectedValue}
          onChange={(event) =>
            onChange(item.original_header, event.target.value)
          }
          className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-3 text-sm text-white outline-none transition focus:border-slate-400"
        >
          <option value="">Leave this out</option>
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
  onRowOverrideChange: (
    rowNumber: number,
    fieldName: string,
    value: string,
  ) => void;
  onApplyRowFix: (rowNumber: number) => void;
}) {
  const hasError = row.issues.some((issue) => issue.severity === "error");
  const needsFollowUpFix = row.issues.some(
    (issue) =>
      issue.field === "next_follow_up_at" && issue.severity === "error",
  );
  return (
    <article
      className={`rounded-[1.2rem] border px-4 py-4 ${hasError ? "border-rose-300 bg-rose-950/40" : row.duplicate ? "border-amber-300 bg-amber-950/30" : "border-white/10 bg-white/5"}`}
    >
      <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
            Row {row.row_number}
          </p>
          <h4 className="mt-2 text-lg font-semibold text-white">
            {row.lead_name}
          </h4>
          <p className="text-sm text-slate-300">{row.company_name}</p>
          <p className="mt-2 text-xs uppercase tracking-[0.18em] text-slate-400">
            Owner · {row.owner_name}
          </p>
        </div>
        <div className="text-right">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
            {row.stage}
          </p>
          <p className="mt-2 text-sm text-slate-200">
            {formatDateTime(row.next_follow_up_at)}
          </p>
        </div>
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <TimelineTileDark
          label="Priority"
          value={
            row.priority ? `${row.priority} priority` : "Auto after import"
          }
        />
        <TimelineTileDark
          label="Channel"
          value={row.contact_channel || "Spreadsheet default"}
        />
        <TimelineTileDark
          label="Next step"
          value={row.next_step || "Brivoly will draft a default follow-up task"}
        />
      </div>
      {row.notes ? (
        <p className="mt-3 text-sm leading-6 text-slate-300">{row.notes}</p>
      ) : null}
      {row.issues.length ? (
        <div className="mt-3 space-y-2">
          {row.issues.map((issue, index) => (
            <p
              key={`${issue.row_number}-${issue.field ?? "general"}-${index}`}
              className={`rounded-xl px-3 py-2 text-xs ${issue.severity === "error" ? "bg-rose-200 text-rose-950" : "bg-amber-200 text-amber-950"}`}
            >
              {issue.message}
            </p>
          ))}
        </div>
      ) : null}
      {needsFollowUpFix ? (
        <div className="mt-4 rounded-xl border border-cyan-300/30 bg-cyan-400/10 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-200">
            Fix missing data in Brivoly
          </p>
          <div className="mt-3 flex flex-col gap-3 md:flex-row md:items-end">
            <label className="block flex-1">
              <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-300">
                Next follow-up date
              </span>
              <input
                type="datetime-local"
                value={
                  rowOverride?.next_follow_up_at ??
                  formatDateTimeInputValue(row.next_follow_up_at)
                }
                onChange={(event) =>
                  onRowOverrideChange(
                    row.row_number,
                    "next_follow_up_at",
                    event.target.value,
                  )
                }
                className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-3 text-sm text-white outline-none transition focus:border-slate-400"
              />
            </label>
            <Button
              variant="outline"
              onClick={() => onApplyRowFix(row.row_number)}
            >
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
  canSendFromMailbox,
  selectedThread,
  preferredMailboxConnection,
  draftFocusToken,
  onEmailObjectiveChange,
  onEmailToneChange,
  onEmailLengthChange,
  onEmailSubjectDraftChange,
  onEmailBodyDraftChange,
  onGenerateEmailDraft,
  onSendDraftToMailbox,
  initialMemoryView,
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
  canSendFromMailbox: boolean;
  selectedThread: CRMLeadFollowUp["recent_email_threads"][number] | null;
  preferredMailboxConnection: CRMMailboxConnection | null;
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
  onSendDraftToMailbox: () => void;
  initialMemoryView?: "meeting_prep" | null;
}) {
  const launchHref = buildMailtoHref(emailSubjectDraft, emailBodyDraft);
  const suggestedResponses = buildSuggestedResponsePresets(lead);
  const composerSectionRef = useRef<HTMLElement | null>(null);
  const storySpineSectionRef = useRef<HTMLElement | null>(null);
  const keyMomentsSectionRef = useRef<HTMLElement | null>(null);
  const uploadHistorySectionRef = useRef<HTMLElement | null>(null);
  const fullTimelineSectionRef = useRef<HTMLElement | null>(null);
  const threadProviderMismatch = Boolean(
    selectedThread &&
    preferredMailboxConnection &&
    selectedThread.source !== preferredMailboxConnection.provider,
  );
  const threadProviderLabel =
    selectedThread?.source === "gmail"
      ? "Gmail"
      : selectedThread?.source === "outlook"
        ? "Outlook"
        : null;
  const sendProviderLabel =
    preferredMailboxConnection?.provider === "gmail"
      ? "Gmail"
      : preferredMailboxConnection?.provider === "outlook"
        ? "Outlook"
        : null;
  const [memoryView, setMemoryView] = useState<
    | "overview"
    | "last_30_days"
    | "meeting_prep"
    | "recent_changes"
    | "recent_upload"
  >(initialMemoryView ?? "overview");
  const latestTimelineEntry = getLatestContextEntry(lead);
  const latestUploadEntry = getLatestUploadContextEntry(lead);
  const latestMeaningfulEntry = getLatestMeaningfulTimelineEntry(lead);
  const keyTimelineMoments = getKeyTimelineMoments(lead);
  const uploadTimelineEntries = getUploadTimelineEntries(lead);
  const latestThread = selectedThread ?? getNewestThread(lead);
  const prepOpenLoop =
    latestThread?.open_loop ||
    latestThread?.unresolved_hint ||
    lead.relationship_reconnect_next_move ||
    lead.next_step ||
    "No meeting carry-forward was captured yet.";
  const prepFreshContext =
    lead.relationship_recent_upload_summary ||
    (latestUploadEntry
      ? `${formatDateTime(latestUploadEntry.occurred_at)} · ${latestUploadEntry.summary}`
      : "No recent client-shared context.");
  const prepRecentShift =
    latestThread?.recent_change_hint ||
    latestThread?.continuity_memory ||
    (latestMeaningfulEntry
      ? `${formatTimelineEntryLabel(latestMeaningfulEntry)} · ${latestMeaningfulEntry.summary}`
      : "No recent relationship shift was captured yet.");
  const prepBestOpening =
    latestThread?.next_touch_hint ||
    lead.relationship_meeting_prep_summary ||
    lead.relationship_upload_follow_through_hint ||
    "Brivoly is holding the latest relationship context for the next conversation.";
  const storyOpenLoop =
    selectedThread?.open_loop ||
    selectedThread?.unresolved_hint ||
    latestThread?.open_loop ||
    latestThread?.unresolved_hint ||
    lead.next_step ||
    "No open loop captured yet.";
  const storyNextTouch =
    lead.relationship_upload_follow_through_hint ||
    lead.relationship_reconnect_next_move ||
    latestThread?.next_touch_hint ||
    lead.next_step;
  const memoryPanels = [
    {
      value: "overview" as const,
      label: "What matters",
      body:
        lead.relationship_context_summary || lead.notes || "No summary yet.",
    },
    {
      value: "last_30_days" as const,
      label: "Last 30 days",
      body: lead.relationship_last_30_days_summary || "No 30-day summary yet.",
    },
    {
      value: "meeting_prep" as const,
      label: "Meeting prep",
      body:
        lead.relationship_meeting_prep_summary ||
        "No meeting prep summary yet.",
    },
    {
      value: "recent_changes" as const,
      label: "What changed",
      body:
        lead.relationship_recent_changes_summary ||
        "No recent changes were captured yet.",
    },
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
  const activeMemoryPanel =
    memoryPanels.find((item) => item.value === memoryView) ?? memoryPanels[0];

  useEffect(() => {
    if (!draftFocusToken) {
      return;
    }
    composerSectionRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }, [draftFocusToken, lead.id]);

  useEffect(() => {
    if (initialMemoryView) {
      setMemoryView(initialMemoryView);
    }
  }, [initialMemoryView, lead.id]);

  const jumpToSection = (section: { current: HTMLElement | null }) => {
    section.current?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  };

  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
        Relationship memory
      </p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">
        {lead.lead_name}
      </h2>
      <p className="mt-1 text-sm text-slate-600">{lead.company_name}</p>
      {selectedThread ? (
        <p className="mt-2 text-sm leading-6 text-slate-600">
          Drafting inside{" "}
          <span className="font-medium text-slate-900">
            {selectedThread.subject}
          </span>
          {preferredMailboxConnection
            ? ` through ${preferredMailboxConnection.provider === "gmail" ? "Gmail" : "Outlook"}.`
            : "."}
        </p>
      ) : null}
      {threadProviderMismatch && threadProviderLabel && sendProviderLabel ? (
        <p className="mt-2 rounded-[1rem] border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-900">
          No {threadProviderLabel} mailbox is connected for this thread right
          now, so Brivoly will send through {sendProviderLabel} and keep the
          thread attached in relationship memory.
        </p>
      ) : null}

      <section className="mt-6 rounded-[1.5rem] border bg-slate-50/85 p-5">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
          What matters now
        </p>
        <h3 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
          Open with the relationship story, not the status.
        </h3>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          Brivoly keeps the latest saved moment, the open loop, and the cleanest
          next touch together so you can step back in without piecing the story
          together first.
        </p>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <TimelineTile
            label="Latest saved moment"
            value={
              latestMeaningfulEntry
                ? `${formatTimelineEntryLabel(latestMeaningfulEntry)} · ${latestMeaningfulEntry.summary}`
                : "No relationship history saved yet."
            }
          />
          <TimelineTile label="Open loop" value={storyOpenLoop} />
          <TimelineTile label="Best next touch" value={storyNextTouch} />
          <TimelineTile
            label="Latest client-shared context"
            value={
              latestUploadEntry
                ? `${formatDateTime(latestUploadEntry.occurred_at)} · ${latestUploadEntry.summary}`
                : "No recent client-shared context."
            }
          />
        </div>
        <div className="mt-4 flex flex-wrap gap-3">
          <Button
            type="button"
            variant="outline"
            onClick={() => setMemoryView("recent_changes")}
          >
            Review recent changes
          </Button>
          {lead.relationship_recent_upload_summary ? (
            <Button
              type="button"
              variant="outline"
              onClick={() => setMemoryView("recent_upload")}
            >
              Use client-shared context
            </Button>
          ) : null}
          {lead.relationship_upcoming_meeting_at ? (
            <Button
              type="button"
              variant="outline"
              onClick={() => setMemoryView("meeting_prep")}
            >
              Prepare from continuity
            </Button>
          ) : null}
        </div>
        <div className="mt-4 rounded-[1rem] border bg-white px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">
            Jump into the story
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => jumpToSection(storySpineSectionRef)}
              className="rounded-full border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-700 transition hover:border-slate-400 hover:bg-white hover:text-slate-950"
            >
              Start with the story spine
            </button>
            {keyTimelineMoments.length ? (
              <button
                type="button"
                onClick={() => jumpToSection(keyMomentsSectionRef)}
                className="rounded-full border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-700 transition hover:border-slate-400 hover:bg-white hover:text-slate-950"
              >
                Key moments
              </button>
            ) : null}
            {uploadTimelineEntries.length ? (
              <button
                type="button"
                onClick={() => jumpToSection(uploadHistorySectionRef)}
                className="rounded-full border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-700 transition hover:border-slate-400 hover:bg-white hover:text-slate-950"
              >
                Client-shared history
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => jumpToSection(fullTimelineSectionRef)}
              className="rounded-full border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-700 transition hover:border-slate-400 hover:bg-white hover:text-slate-950"
            >
              Full timeline
            </button>
            <button
              type="button"
              onClick={() => jumpToSection(composerSectionRef)}
              className="rounded-full border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-700 transition hover:border-slate-400 hover:bg-white hover:text-slate-950"
            >
              Composer
            </button>
          </div>
        </div>
      </section>

      <div className="mt-5 grid gap-3 md:grid-cols-2">
        <TimelineTile
          label="Relationship read"
          value={`${formatRelationshipState(lead.relationship_state)} · ${formatStageLabel(lead.stage)}`}
        />
        <TimelineTile label="Best channel" value={lead.contact_channel} />
        <TimelineTile label="Point person" value={lead.owner_name} />
        {lead.relationship_upcoming_meeting_at ? (
          <TimelineTile
            label="Upcoming meeting"
            value={`${formatDateTime(lead.relationship_upcoming_meeting_at)}${lead.relationship_upcoming_meeting_label ? ` · ${lead.relationship_upcoming_meeting_label}` : ""}`}
          />
        ) : null}
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <TimelineTile
          label="Last meaningful interaction"
          value={formatDateTime(lead.last_meaningful_interaction_at)}
        />
        <TimelineTile
          label="Why now"
          value={getLeadCardWhyNow(lead)}
        />
        <TimelineTile
          label="Brivoly nudge"
          value={
            lead.relationship_upload_follow_through_hint ||
            lead.relationship_timing_nudge ||
            "Brivoly is keeping the timing in view."
          }
        />
      </div>

      {lead.relationship_upcoming_meeting_at ? (
        <section className="mt-6 rounded-[1.5rem] border bg-emerald-50/70 p-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-2xl">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-700">
                Upcoming meeting
              </p>
              <h3 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                Walk into this conversation with the right context already
                loaded.
              </h3>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                {lead.relationship_upcoming_meeting_label ||
                  "Brivoly found a meeting-like next step for this relationship."}
                {lead.relationship_upcoming_meeting_source
                  ? ` Source: ${lead.relationship_upcoming_meeting_source}.`
                  : ""}
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Button
                type="button"
                onClick={() => setMemoryView("meeting_prep")}
              >
                Prepare me
              </Button>
            </div>
          </div>
        </section>
      ) : null}

      {(lead.relationship_upcoming_meeting_at || memoryView === "meeting_prep") && (
        <section className="mt-6 rounded-[1.5rem] border bg-emerald-50/40 p-5">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-700">
            Prepare from continuity
          </p>
          <h3 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
            Bring the thread, the latest shift, and the client context into one view.
          </h3>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
            Brivoly keeps the upcoming meeting, the freshest conversation signal,
            and the carry-forward context side by side so you can walk in
            oriented without piecing the story back together.
          </p>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <TimelineTile
              label="Meeting moment"
              value={
                lead.relationship_upcoming_meeting_at
                  ? `${formatDateTime(lead.relationship_upcoming_meeting_at)}${lead.relationship_upcoming_meeting_label ? ` · ${lead.relationship_upcoming_meeting_label}` : ""}`
                  : "No upcoming meeting is scheduled yet."
              }
            />
            <TimelineTile label="Freshest shift" value={prepRecentShift} />
            <TimelineTile label="Carry into the room" value={prepOpenLoop} />
            <TimelineTile label="Best opening" value={prepBestOpening} />
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <TimelineTile
              label="Client-shared context"
              value={prepFreshContext}
            />
            <TimelineTile
              label="Latest saved moment"
              value={
                latestMeaningfulEntry
                  ? `${formatTimelineEntryLabel(latestMeaningfulEntry)} · ${latestMeaningfulEntry.summary}`
                  : "No saved relationship moment yet."
              }
            />
          </div>
          {latestThread ? (
            <div className="mt-4 rounded-[1.2rem] border bg-white px-4 py-4">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                Thread to keep in view
              </p>
              <p className="mt-2 text-sm font-medium text-slate-900">
                {latestThread.subject}
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-700">
                {latestThread.relationship_pulse}
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                {latestThread.memory_summary}
              </p>
              {latestThread.carry_forward_hint ? (
                <p className="mt-2 text-sm leading-6 text-slate-700">
                  {latestThread.carry_forward_hint}
                </p>
              ) : null}
            </div>
          ) : null}
        </section>
      )}

      {isReconnectMoment(lead) ? (
        <section className="mt-6 rounded-[1.5rem] border bg-sky-50/70 p-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-2xl">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-700">
                Gentle re-entry
              </p>
              <h3 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                Reopen this relationship without sounding abrupt.
              </h3>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                Brivoly is surfacing a low-pressure path back in so you do not
                have to reconstruct the opening from scratch.
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
            <TimelineTile
              label="Why now"
              value={
                lead.relationship_reconnect_why_now ||
                lead.relationship_timing_nudge ||
                "Brivoly is keeping a reconnect path ready."
              }
            />
            <TimelineTile
              label="Why it can still land"
              value={describeReconnectWindow(lead)}
            />
            <TimelineTile
              label="Best re-entry"
              value={lead.relationship_reconnect_next_move || lead.next_step}
            />
            <TimelineTile
              label="Starter line"
              value={buildReconnectStarterLine(lead)}
            />
            <TimelineTile
              label="If it stays quiet"
              value={buildReconnectFallbackStep(lead)}
            />
          </div>
          <div className="mt-4 flex flex-wrap gap-3">
            <Button
              type="button"
              variant="outline"
              onClick={() => setMemoryView("recent_changes")}
            >
              Review recent changes
            </Button>
            {lead.relationship_recent_upload_summary ? (
              <Button
                type="button"
                variant="outline"
                onClick={() => setMemoryView("recent_upload")}
              >
                Use client-shared context
              </Button>
            ) : null}
          </div>
        </section>
      ) : null}

      {lead.referral_source_name ||
      lead.birthday ||
      lead.company_milestone_date ||
      lead.relationship_reminders.length ? (
        <section className="mt-6 rounded-[1.5rem] border bg-amber-50/70 p-5">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-amber-700">
            Keep this relationship warm
          </p>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <TimelineTile
              label="Warm intro source"
              value={lead.referral_source_name || "No warm intro mapped yet"}
            />
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
                <RelationshipReminderCard
                  key={`${reminder.kind}-${reminder.title}-${reminder.due_at ?? "none"}`}
                  reminder={reminder}
                />
              ))}
            </div>
          ) : null}
        </section>
      ) : null}

      <section
        ref={storySpineSectionRef}
        className="mt-6 rounded-[1.5rem] border bg-white p-5"
      >
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
          Story spine
        </p>
        <h3 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
          Read the relationship in one pass before drafting.
        </h3>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          This is the shortest route through what happened, what shifted, what
          still needs attention, and where the next note should begin.
        </p>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <TimelineTile
            label="What happened"
            value={
              latestMeaningfulEntry
                ? `${formatTimelineEntryLabel(latestMeaningfulEntry)} · ${latestMeaningfulEntry.summary}`
                : "No saved relationship history yet."
            }
          />
          <TimelineTile label="What changed" value={prepRecentShift} />
          <TimelineTile label="What still needs attention" value={storyOpenLoop} />
          <TimelineTile label="Where the next note starts" value={storyNextTouch} />
        </div>
      </section>

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
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
            {activeMemoryPanel.label}
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-700">
            {activeMemoryPanel.body}
          </p>
          {memoryView === "meeting_prep" ? (
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <TimelineTile label="Carry into the room" value={prepOpenLoop} />
              <TimelineTile label="Freshest shift" value={prepRecentShift} />
            </div>
          ) : null}
        </div>
        <div className="mt-4 rounded-[1.2rem] border bg-white px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
            Context on hand
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-700">{lead.notes}</p>
          {lead.relationship_recent_upload_summary ? (
            <div className="mt-4 rounded-[1rem] border bg-slate-50/80 px-4 py-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">
                Recent upload context
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-700">
                {lead.relationship_recent_upload_summary}
              </p>
              {lead.relationship_upload_follow_through_hint ? (
                <p className="mt-3 text-sm leading-6 text-slate-700">
                  {lead.relationship_upload_follow_through_hint}
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
        {lead.relationship_recent_upload_summary &&
        memoryView !== "meeting_prep" ? (
          <div className="mt-4 rounded-[1.2rem] border bg-white px-4 py-4">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
              Meeting prep from fresh context
            </p>
            <p className="mt-2 text-sm leading-6 text-slate-700">
              {lead.relationship_meeting_prep_summary}
            </p>
          </div>
        ) : null}
      </section>

      {keyTimelineMoments.length ? (
        <section
          ref={keyMomentsSectionRef}
          className="mt-6 rounded-[1.5rem] border bg-white p-5"
        >
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
            Key moments
          </p>
          <h3 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
            The moments most likely to shape the next touch.
          </h3>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            {keyTimelineMoments.map((entry) => (
              <StoryMomentCard key={`story-${entry.id}`} entry={entry} />
            ))}
          </div>
        </section>
      ) : null}

      {uploadTimelineEntries.length ? (
        <section
          ref={uploadHistorySectionRef}
          className="mt-6 rounded-[1.5rem] border bg-sky-50/50 p-5"
        >
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-700">
            Client-shared history
          </p>
          <h3 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
            Keep the client’s updates attached to the relationship story.
          </h3>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
            Screenshots, whiteboard photos, and handoff notes stay visible here
            so the next reply can start from what the client actually sent, not
            from memory alone.
          </p>
          <div className="mt-4 space-y-3">
            {uploadTimelineEntries.slice(0, 3).map((entry, index) => (
              <div
                key={`upload-story-${entry.id}`}
                className="rounded-[1.2rem] border bg-white px-4 py-4"
              >
                <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-700">
                      Client-shared context
                    </p>
                    <MiniFlag
                      label={formatUploadHistorySource(entry)}
                      tone="neutral"
                    />
                    {index === 0 ? (
                      <MiniFlag label="Latest" tone="neutral" />
                    ) : null}
                  </div>
                  <p className="text-xs text-slate-500">
                    {formatDateTime(entry.occurred_at)}
                  </p>
                </div>
                <p className="mt-3 text-sm leading-6 text-slate-700">
                  {entry.summary}
                </p>
                {index === 0 && lead.relationship_upload_follow_through_hint ? (
                  <div className="mt-3 rounded-[1rem] border bg-sky-50/70 px-4 py-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-sky-700">
                      Use this in the next touch
                    </p>
                    <p className="mt-2 text-sm leading-6 text-slate-700">
                      {lead.relationship_upload_follow_through_hint}
                    </p>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <section
        ref={fullTimelineSectionRef}
        className="mt-6 rounded-[1.5rem] border bg-white p-5"
      >
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
          Full timeline
        </p>
        <h3 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
          Read the relationship story before you write the next note.
        </h3>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          The timeline is the running memory of what happened, what changed,
          and what Brivoly thinks matters now.
        </p>
        <div className="mt-4 space-y-4">
          {lead.timeline.map((entry) => {
            const uploadContext = isUploadTimelineEntry(entry);
            return (
              <div
                key={entry.id}
                className={`rounded-[1.35rem] border p-4 ${
                  uploadContext
                    ? "border-sky-200 bg-sky-50/80"
                    : "bg-slate-50/80"
                }`}
              >
                <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                  <div className="flex flex-wrap items-center gap-2">
                    <p
                      className={`text-xs font-semibold uppercase tracking-[0.2em] ${uploadContext ? "text-sky-700" : "text-slate-400"}`}
                    >
                      {uploadContext
                        ? "client-shared context"
                        : `${entry.kind.replaceAll("_", " ")} · ${entry.channel}`}
                    </p>
                    {uploadContext ? (
                      <MiniFlag
                        label={formatUploadHistorySource(entry)}
                        tone="neutral"
                      />
                    ) : null}
                  </div>
                  <p className="text-xs text-slate-500">
                    {formatDateTime(entry.occurred_at)}
                  </p>
                </div>
                <p className="mt-3 text-sm leading-6 text-slate-700">
                  {entry.summary}
                </p>
              </div>
            );
          })}
        </div>
      </section>

      <section
        ref={composerSectionRef}
        className="mt-6 rounded-[1.5rem] border bg-white p-5"
      >
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="ui-eyebrow">Suggested next note</p>
            <h3 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
              Draft the next note without starting from zero.
            </h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              Brivoly uses the latest context, suggested next touch, and your
              saved business profile to suggest a message you can edit before
              sending.
            </p>
          </div>
          <div className="rounded-[1.2rem] border bg-slate-50 px-4 py-3 text-sm text-slate-600 lg:max-w-xs">
            <p className="ui-eyebrow">Sent from</p>
            <p className="mt-2">
              Sender:{" "}
              <span className="font-medium text-slate-900">
                {settings?.outbound_sender_name ||
                  settings?.business_name ||
                  "Fallback defaults"}
              </span>
            </p>
          </div>
        </div>

        <div className="mt-5 rounded-[1.2rem] border bg-slate-50/80 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
            Ways to say it
          </p>
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
          <p className="mt-3 text-xs text-slate-500">
            Pick the message shape that fits this moment, then edit before
            sending.
          </p>
        </div>

        <div className="mt-5 grid gap-4 xl:grid-cols-3">
          <label className="block">
            <span className="ui-eyebrow">Objective</span>
            <select
              value={emailObjective}
              onChange={(event) =>
                onEmailObjectiveChange(
                  event.target.value as CRMEmailDraft["objective"],
                )
              }
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
              onChange={(event) =>
                onEmailToneChange(event.target.value as CRMEmailDraft["tone"])
              }
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
              onChange={(event) =>
                onEmailLengthChange(
                  event.target.value as CRMEmailDraft["length"],
                )
              }
              className="mt-2 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400 focus:bg-white"
            >
              <option value="short">Short</option>
              <option value="medium">Medium</option>
            </select>
          </label>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <Button
            onClick={() => onGenerateEmailDraft()}
            disabled={isGeneratingEmail}
          >
            {isGeneratingEmail
              ? "Drafting..."
              : emailDraft
                ? "Refresh draft"
                : "Draft note"}
          </Button>
          {canSendFromMailbox ? (
            <Button
              variant="outline"
              onClick={onSendDraftToMailbox}
              disabled={
                isGeneratingEmail ||
                !emailSubjectDraft.trim() ||
                !emailBodyDraft.trim()
              }
            >
              Send from mailbox
            </Button>
          ) : null}
          {launchHref ? (
            <a
              href={launchHref}
              className="inline-flex items-center rounded-full border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-slate-500 hover:text-slate-950"
            >
              Open in email app
            </a>
          ) : null}
          {emailStatus ? (
            <p className="text-sm text-slate-500">{emailStatus}</p>
          ) : null}
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
                onChange={(event) =>
                  onEmailSubjectDraftChange(event.target.value)
                }
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
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
          Keep the memory current
        </p>
        <textarea
          value={noteDraft}
          onChange={(event) => onNoteDraftChange(event.target.value)}
          placeholder="Capture what changed, what matters, or what you will want to remember before the next touch."
          className="mt-3 min-h-28 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-slate-400 focus:bg-white"
        />
        <div className="mt-4 flex items-center justify-between gap-4">
          <p className="text-xs text-slate-500">
            Keep notes light. This is here to preserve context, not create more
            work.
          </p>
          <Button
            disabled={isSavingNote || !noteDraft.trim()}
            onClick={onSaveNote}
          >
            {isSavingNote ? "Saving..." : "Save note"}
          </Button>
        </div>
      </section>

    </section>
  );
}

function RelationshipSignalsPanel({
  summary,
}: {
  summary: NonNullable<CRMFollowUpOverview["relationship_summary"]>;
}) {
  const needsAttention =
    summary.drifting_count + summary.stale_count + summary.at_risk_count;
  const warmMoments =
    summary.referral_reminder_count + summary.milestone_reminder_count;
  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
        Relationship posture
      </p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">
        A calmer read on which relationships are steady and which ones need
        warmth.
      </h2>
      <div className="mt-5 space-y-3">
        <TimelineTile
          label="Holding steady"
          value={`${summary.active_count + summary.warm_count} relationship${summary.active_count + summary.warm_count === 1 ? "" : "s"} still feel warm or active`}
        />
        <TimelineTile
          label="Needs attention"
          value={
            needsAttention
              ? `${needsAttention} relationship${needsAttention === 1 ? "" : "s"} may need a warmer touch soon`
              : "Nothing feels especially fragile right now"
          }
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

function WarmIntroGraphPanel({
  summary,
}: {
  summary: NonNullable<CRMFollowUpOverview["relationship_summary"]>;
}) {
  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
        Warm ways back in
      </p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">
        Know who can help you reopen a quiet relationship more naturally.
      </h2>
      <p className="mt-3 text-sm leading-6 text-slate-600">
        When a past intro or referral gives you a softer re-entry path, Brivoly
        keeps it close instead of leaving it buried in old notes.
      </p>
      <div className="mt-5 grid gap-3 md:grid-cols-2">
        {summary.warm_intro_connections.length ? (
          summary.warm_intro_connections.map((connection) => (
            <div
              key={`${connection.source_name}-${connection.target_lead_id}`}
              className="rounded-[1.2rem] border bg-slate-50/80 px-4 py-4"
            >
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                {connection.source_name}
              </p>
              <p className="mt-2 text-sm text-slate-700">
                could help reopen{" "}
                <span className="font-medium text-slate-950">
                  {connection.target_lead_name}
                </span>{" "}
                at {connection.target_company_name}
              </p>
              <p className="mt-2 text-xs text-slate-500">
                Best person to pick it up: {connection.owner_name}
              </p>
            </div>
          ))
        ) : (
          <div className="rounded-[1.2rem] border border-dashed bg-slate-50/80 px-4 py-4 text-sm text-slate-600">
            No warm intro links are mapped yet. When you save referral context
            on a relationship, Brivoly can turn it into a softer path back in
            later.
          </div>
        )}
      </div>
    </section>
  );
}

function RelationshipReminderCard({
  reminder,
}: {
  reminder: CRMRelationshipReminder;
}) {
  return (
    <div className="rounded-[1.2rem] border border-amber-200 bg-white/80 px-4 py-4">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-700">
          {formatReminderKind(reminder.kind)}
        </p>
        <p className="text-xs text-slate-500">
          {reminder.due_at
            ? formatDateTime(reminder.due_at)
            : "No due time set"}
        </p>
      </div>
      <p className="mt-2 text-sm font-medium text-slate-900">
        {reminder.title}
      </p>
      <p className="mt-2 text-sm leading-6 text-slate-700">
        {reminder.message}
      </p>
    </div>
  );
}

function StoryMomentCard({
  entry,
}: {
  entry: CRMLeadFollowUp["timeline"][number];
}) {
  const uploadContext = isUploadTimelineEntry(entry);
  return (
    <div
      className={`rounded-[1.2rem] border px-4 py-4 ${
        uploadContext
          ? "border-sky-200 bg-sky-50/80"
          : "border-slate-200 bg-slate-50/80"
      }`}
    >
      <p
        className={`text-xs font-semibold uppercase tracking-[0.18em] ${
          uploadContext ? "text-sky-700" : "text-slate-400"
        }`}
      >
        {formatTimelineEntryLabel(entry)}
      </p>
      <p className="mt-2 text-sm font-medium text-slate-950">
        {formatDateTime(entry.occurred_at)}
      </p>
      <p className="mt-3 text-sm leading-6 text-slate-700">{entry.summary}</p>
    </div>
  );
}

function MiniFlag({
  label,
  tone,
}: {
  label: string;
  tone: "warning" | "critical" | "neutral";
}) {
  return (
    <span
      className={`inline-flex max-w-full items-center rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] [overflow-wrap:anywhere] ${
        tone === "critical"
          ? "bg-rose-100 text-rose-800"
          : tone === "warning"
            ? "bg-amber-100 text-amber-800"
            : "bg-slate-100 text-slate-700"
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

function MetricCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "neutral" | "warning" | "critical" | "positive";
}) {
  const toneClass =
    tone === "positive"
      ? "border-emerald-200 bg-emerald-50 text-emerald-900"
      : tone === "warning"
        ? "border-amber-200 bg-amber-50 text-amber-900"
        : tone === "critical"
          ? "border-rose-200 bg-rose-50 text-rose-900"
          : "border-slate-200 bg-white text-slate-900";

  return (
    <div
      className={`min-w-0 overflow-hidden rounded-[1.4rem] border p-5 shadow-sm ${toneClass}`}
    >
      <p className="break-words text-xs font-semibold uppercase tracking-[0.14em] [overflow-wrap:anywhere] sm:tracking-[0.2em]">
        {label}
      </p>
      <p className="mt-3 break-words text-3xl font-semibold tracking-tight [overflow-wrap:anywhere]">
        {value}
      </p>
    </div>
  );
}

function CompactMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 overflow-hidden rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
      <p className="break-words text-xs font-semibold uppercase tracking-[0.14em] text-slate-400 [overflow-wrap:anywhere] sm:tracking-[0.18em]">
        {label}
      </p>
      <p className="mt-2 break-words text-xl font-semibold text-white [overflow-wrap:anywhere]">
        {value}
      </p>
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
    <div
      className={`min-w-0 overflow-hidden rounded-2xl border px-4 py-3 ${className}`}
    >
      <p className="break-words text-xs font-semibold uppercase tracking-[0.14em] [overflow-wrap:anywhere] sm:tracking-[0.18em]">
        {label}
      </p>
      <p className="mt-2 break-words text-xl font-semibold [overflow-wrap:anywhere]">
        {value}
      </p>
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
    <div
      className={`inline-flex max-w-full rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] [overflow-wrap:anywhere] sm:tracking-[0.2em] ${className}`}
    >
      {priority} priority
    </div>
  );
}

function TimelineTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 overflow-hidden rounded-2xl border bg-white px-4 py-3">
      <p className="break-words text-xs font-semibold uppercase tracking-[0.14em] text-slate-400 [overflow-wrap:anywhere] sm:tracking-[0.2em]">
        {label}
      </p>
      <p className="mt-2 break-words text-sm text-slate-700 [overflow-wrap:anywhere]">
        {value}
      </p>
    </div>
  );
}

function TimelineTileDark({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 overflow-hidden rounded-2xl border border-white/10 bg-slate-900/40 px-4 py-3">
      <p className="break-words text-xs font-semibold uppercase tracking-[0.14em] text-slate-400 [overflow-wrap:anywhere] sm:tracking-[0.2em]">
        {label}
      </p>
      <p className="mt-2 break-words text-sm text-slate-200 [overflow-wrap:anywhere]">
        {value}
      </p>
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
  if (
    item.relationship_state === "at_risk" ||
    item.relationship_state === "drifting"
  ) {
    return `${item.lead_name} needs a warmer touch`;
  }
  return `Next touch for ${item.lead_name}`;
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
  const timestamps = item.recent_email_threads
    .map((thread) => new Date(thread.last_message_at).getTime())
    .filter((value) => !Number.isNaN(value));
  if (!timestamps.length) {
    return null;
  }
  return new Date(Math.max(...timestamps)).toISOString();
}

function getLatestContextEntry(item: CRMLeadFollowUp) {
  return getSortedTimelineEntries(item)[0] ?? null;
}

function getLatestUploadContextEntry(item: CRMLeadFollowUp) {
  return getUploadTimelineEntries(item)[0] ?? null;
}

function getSortedTimelineEntries(item: CRMLeadFollowUp) {
  const timeline = [...item.timeline];
  timeline.sort(
    (left, right) =>
      new Date(right.occurred_at).getTime() -
      new Date(left.occurred_at).getTime(),
  );
  return timeline;
}

function getUploadTimelineEntries(item: CRMLeadFollowUp) {
  return getSortedTimelineEntries(item).filter((entry) => isUploadTimelineEntry(entry));
}

function getLatestMeaningfulTimelineEntry(item: CRMLeadFollowUp) {
  return (
    getSortedTimelineEntries(item).find((entry) =>
      isMeaningfulTimelineEntry(entry),
    ) ??
    getSortedTimelineEntries(item)[0] ??
    null
  );
}

function getKeyTimelineMoments(item: CRMLeadFollowUp) {
  return getSortedTimelineEntries(item)
    .filter((entry) => isMeaningfulTimelineEntry(entry))
    .slice(0, 3);
}

function getReplySummary(item: CRMLeadFollowUp) {
  const replyThread = item.recent_email_threads.find(
    (thread) => thread.needs_reply,
  );
  if (!replyThread) {
    return item.next_step;
  }
  return replyThread.snippet || item.next_step;
}

function getReplyThread(item: CRMLeadFollowUp) {
  return (
    [...item.recent_email_threads]
      .filter((thread) => thread.needs_reply)
      .sort(
        (left, right) =>
          new Date(right.last_message_at).getTime() -
          new Date(left.last_message_at).getTime(),
      )[0] ?? null
  );
}

function compareReplyPriority(left: CRMLeadFollowUp, right: CRMLeadFollowUp) {
  return (
    getNewestThreadTimestamp(right) - getNewestThreadTimestamp(left) ||
    compareSoonestFollowUp(left, right)
  );
}

function compareReconnectPriority(
  left: CRMLeadFollowUp,
  right: CRMLeadFollowUp,
) {
  return (
    relationshipStateUrgency(right.relationship_state) -
      relationshipStateUrgency(left.relationship_state) ||
    getLastMeaningfulTimestamp(left) - getLastMeaningfulTimestamp(right) ||
    compareSoonestFollowUp(left, right)
  );
}

function compareProposalPriority(
  left: CRMLeadFollowUp,
  right: CRMLeadFollowUp,
) {
  return (
    Number(right.priority === "high") - Number(left.priority === "high") ||
    compareSoonestFollowUp(left, right) ||
    getLastMeaningfulTimestamp(right) - getLastMeaningfulTimestamp(left)
  );
}

function compareFreshContextPriority(
  left: CRMLeadFollowUp,
  right: CRMLeadFollowUp,
) {
  return getLatestContextTimestamp(right) - getLatestContextTimestamp(left);
}

function compareRecentUploadPriority(
  left: CRMLeadFollowUp,
  right: CRMLeadFollowUp,
) {
  return (
    getLatestUploadContextTimestamp(right) -
    getLatestUploadContextTimestamp(left)
  );
}

function compareSoonestFollowUp(left: CRMLeadFollowUp, right: CRMLeadFollowUp) {
  return (
    new Date(left.next_follow_up_at).getTime() -
    new Date(right.next_follow_up_at).getTime()
  );
}

function getNewestThreadTimestamp(item: CRMLeadFollowUp) {
  return getNewestThreadTime(item)
    ? new Date(getNewestThreadTime(item) as string).getTime()
    : 0;
}

function getLastMeaningfulTimestamp(item: CRMLeadFollowUp) {
  return item.last_meaningful_interaction_at
    ? new Date(item.last_meaningful_interaction_at).getTime()
    : 0;
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

function hasOpenLoop(item: CRMLeadFollowUp) {
  return item.recent_email_threads.some((thread) =>
    Boolean(thread.open_loop.trim() || thread.unresolved_hint.trim()),
  );
}

function getLeadCardWhyNow(item: CRMLeadFollowUp) {
  if (item.recent_email_threads.some((thread) => thread.needs_reply)) {
    return (
      getReplyThread(item)?.next_touch_hint ||
      getReplyThread(item)?.open_loop ||
      "There is an active thread waiting on you."
    );
  }
  if (isReconnectMoment(item)) {
    return (
      item.relationship_reconnect_why_now ||
      item.relationship_timing_nudge ||
      describeReconnectWindow(item)
    );
  }
  if (hasRecentUploadContext(item)) {
    return (
      item.relationship_upload_follow_through_hint ||
      item.relationship_recent_upload_summary ||
      "Fresh client context gives you a natural way back in."
    );
  }
  return item.relationship_timing_nudge || item.next_step;
}

function getNewestThread(item: CRMLeadFollowUp) {
  return (
    [...item.recent_email_threads].sort(
      (left, right) =>
        new Date(right.last_message_at).getTime() -
        new Date(left.last_message_at).getTime(),
    )[0] ?? null
  );
}

function buildThreadOneRead(thread: CRMLeadFollowUp["recent_email_threads"][number]) {
  const parts = [
    thread.continuity_memory,
    thread.recent_change_hint,
    thread.memory_summary,
  ].filter((value) => value.trim());
  return parts[0] || "No conversation memory was captured yet.";
}

function buildThreadReplyAngle(
  thread: CRMLeadFollowUp["recent_email_threads"][number],
) {
  return (
    thread.open_loop ||
    thread.unresolved_hint ||
    thread.carry_forward_hint ||
    thread.next_touch_hint ||
    thread.memory_summary ||
    "No clear reply angle was captured yet."
  );
}

function getLeadCardStory(item: CRMLeadFollowUp) {
  const latest = getLatestMeaningfulTimelineEntry(item);
  if (!latest) {
    return item.notes || "No saved relationship story yet.";
  }
  return `${formatTimelineEntryLabel(latest)} · ${latest.summary}`;
}

function relationshipStateUrgency(state: string) {
  if (state === "at_risk") {
    return 3;
  }
  if (state === "stale") {
    return 2;
  }
  if (state === "drifting") {
    return 1;
  }
  return 0;
}

function isMeaningfulTimelineEntry(entry: CRMLeadFollowUp["timeline"][number]) {
  return entry.kind !== "internal_note";
}

function compareAttentionPriority(
  left: CRMLeadFollowUp,
  right: CRMLeadFollowUp,
) {
  return (
    Number(right.recent_email_threads.some((thread) => thread.needs_reply)) -
      Number(left.recent_email_threads.some((thread) => thread.needs_reply)) ||
    relationshipStateUrgency(right.relationship_state) -
      relationshipStateUrgency(left.relationship_state) ||
    compareSoonestFollowUp(left, right) ||
    getLastMeaningfulTimestamp(left) - getLastMeaningfulTimestamp(right)
  );
}

function matchesInboxThread(
  item: {
    leadName: string;
    companyName: string;
    stage: string;
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
      message_count: number;
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
  if (filter === "unresolved") {
    return isUnresolvedThread(item.thread);
  }
  if (filter === "long_thread") {
    return isLongThread(item.thread);
  }
  if (filter === "new_from_inbox") {
    return item.stage.trim().toLowerCase() === "inbox";
  }
  return true;
}

function isQuietThread(thread: {
  last_message_at: string;
  needs_reply: boolean;
  waiting_on_contact: boolean;
}) {
  const ageMs = Date.now() - new Date(thread.last_message_at).getTime();
  return (
    !thread.needs_reply &&
    !thread.waiting_on_contact &&
    ageMs >= 1000 * 60 * 60 * 24 * 7
  );
}

function isUnresolvedThread(thread: {
  unresolved_hint: string;
  open_loop: string;
}) {
  return Boolean(thread.unresolved_hint.trim() || thread.open_loop.trim());
}

function isLongThread(thread: { message_count: number }) {
  return thread.message_count >= 5;
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

function formatTimelineEntryLabel(entry: CRMLeadFollowUp["timeline"][number]) {
  if (isUploadTimelineEntry(entry)) {
    return "Client-shared context";
  }
  return `${entry.kind.replaceAll("_", " ")} · ${entry.channel}`;
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

function matchesRelationshipQuery(
  item: CRMLeadFollowUp,
  query: string,
): boolean {
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
    item.relationship_context_summary,
    item.relationship_recent_changes_summary,
    item.relationship_recent_upload_summary,
    item.relationship_timing_nudge,
    item.relationship_reconnect_next_move,
    ...item.recent_email_threads.flatMap((thread) => [
      thread.subject,
      thread.counterpart_email,
      thread.counterpart_name,
      thread.memory_summary,
      thread.open_loop,
      thread.unresolved_hint,
    ]),
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(normalized);
}

function matchesRelationshipFilter(
  item: CRMLeadFollowUp,
  filter: RelationshipFilter,
): boolean {
  if (filter === "all") {
    return true;
  }
  if (filter === "due") {
    return isDueNow(item.next_follow_up_at);
  }
  if (filter === "reply") {
    return item.recent_email_threads.some((thread) => thread.needs_reply);
  }
  if (filter === "fresh_context") {
    return hasFreshContext(item) || hasRecentUploadContext(item);
  }
  if (filter === "open_loop") {
    return hasOpenLoop(item);
  }
  if (filter === "stale") {
    return item.relationship_state === "stale";
  }
  return (
    item.relationship_state === "at_risk" ||
    item.relationship_state === "drifting"
  );
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

function isMailboxTokenExpiringSoon(connection: CRMMailboxConnection) {
  if (
    connection.connection_mode !== "oauth" ||
    !connection.token_expires_at ||
    connection.reauth_required
  ) {
    return false;
  }
  const expiresAt = new Date(connection.token_expires_at).getTime();
  if (Number.isNaN(expiresAt)) {
    return false;
  }
  const now = Date.now();
  return expiresAt > now && expiresAt <= now + 1000 * 60 * 60 * 12;
}

function buildSuggestedResponsePresets(lead: CRMLeadFollowUp) {
  const presets: Array<{
    label: string;
    objective: CRMEmailDraft["objective"];
    tone: CRMEmailDraft["tone"];
    length: CRMEmailDraft["length"];
  }> = [];

  const hasReplyPressure = lead.recent_email_threads.some(
    (thread) => thread.needs_reply,
  );
  const isProposalMoment = lead.stage.trim().toLowerCase() === "proposal";
  const isReconnectionMoment = isReconnectMoment(lead);

  if (hasReplyPressure) {
    presets.push({
      label: "Reply",
      objective: "follow_up",
      tone: "warm",
      length: "short",
    });
    presets.push({
      label: "Schedule",
      objective: "follow_up",
      tone: "direct",
      length: "short",
    });
  }
  if (isProposalMoment) {
    presets.push({
      label: "Proposal nudge",
      objective: "follow_up",
      tone: "confident",
      length: "short",
    });
    presets.push({
      label: "Send recap",
      objective: "recap",
      tone: "warm",
      length: "medium",
    });
  }
  if (isReconnectionMoment) {
    presets.push({
      label: "Reconnect",
      objective: "revive",
      tone: "warm",
      length: "short",
    });
  }

  presets.push({
    label: "Recap",
    objective: "recap",
    tone: "warm",
    length: "medium",
  });
  presets.push({
    label: "Close loop",
    objective: "close_loop",
    tone: "direct",
    length: "short",
  });

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
  return (
    lead.relationship_state === "stale" ||
    lead.relationship_state === "drifting" ||
    lead.relationship_state === "at_risk"
  );
}

function isInboxCreatedRelationship(lead: CRMLeadFollowUp) {
  return (
    lead.stage.trim().toLowerCase() === "inbox" &&
    (Boolean(lead.email_address.trim()) || lead.recent_email_threads.length > 0)
  );
}

function describeReconnectWindow(lead: CRMLeadFollowUp) {
  if (lead.referral_source_name) {
    return `There is still a warmer path here through ${lead.referral_source_name}.`;
  }
  if (lead.relationship_recent_upload_summary) {
    return "Fresh client context gives you a natural reason to step back in.";
  }
  if (
    lead.recent_email_threads.some(
      (thread) =>
        thread.continuity_memory ||
        thread.carry_forward_hint ||
        thread.unresolved_hint,
    )
  ) {
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

function buildReconnectFallbackStep(lead: CRMLeadFollowUp) {
  if (lead.referral_source_name) {
    return `If this lands softly but does not reopen, come back through ${lead.referral_source_name} instead of forcing a colder follow-up.`;
  }
  if (lead.relationship_recent_upload_summary) {
    return "If they stay quiet, follow up by anchoring on the client-shared context instead of sending a generic bump.";
  }
  if (lead.relationship_reminders[0]?.message) {
    return "If this does not reopen the thread yet, wait for the personal or company moment to give you a warmer second reason to reach out.";
  }
  if (
    lead.recent_email_threads.some(
      (thread) => thread.open_loop.trim() || thread.unresolved_hint.trim(),
    )
  ) {
    return "If they stay quiet, close the loop on the last open thread instead of starting over with a brand-new ask.";
  }
  return "If this does not reopen the thread, give it space and let Brivoly hold it until a warmer reason to reach out appears.";
}

function formatReminderKind(value: string) {
  return value.replaceAll("_", " ");
}

function isUploadTimelineEntry(entry: CRMLeadFollowUp["timeline"][number]) {
  const normalizedChannel = entry.channel.trim().toLowerCase();
  return (
    entry.kind === "import" ||
    normalizedChannel === "magic_link" ||
    normalizedChannel === "image" ||
    normalizedChannel === "telegram"
  );
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
  return (
    billing?.enabled === true &&
    ["active", "trialing"].includes(billing.subscription_status ?? "")
  );
}

function formatBillingStatusLabel(status: string | null) {
  if (!status) {
    return "no active subscription";
  }
  return status.replaceAll("_", " ");
}

function isImageFile(fileName: string) {
  const normalized = fileName.toLowerCase();
  return (
    normalized.endsWith(".png") ||
    normalized.endsWith(".jpg") ||
    normalized.endsWith(".jpeg") ||
    normalized.endsWith(".webp")
  );
}
