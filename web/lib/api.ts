import type {
  AccountSettings,
  AlertHistoryResponse,
  BillingOverview,
  CRMEmailDraft,
  CRMFollowUpOverview,
  CRMImportPreview,
  CRMImportResult,
  CRMRemoteIntakeChannel,
  DashboardFilters,
  DashboardSnapshot,
  SessionResponse,
  SettingsBootstrap,
  ShellData,
} from "@/lib/types";

const API_BASE_URL =
  process.env.BRIVOLY_API_BASE_URL ??
  process.env.TRADE_API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://127.0.0.1:8000";

type ApiRequestOptions = {
  sessionToken?: string | null;
  cookieHeader?: string | null;
};

type DashboardRequestOptions = ApiRequestOptions & {
  filters?: Partial<DashboardFilters>;
};

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
  options: ApiRequestOptions = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");

  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (options.sessionToken) {
    headers.set("Authorization", `Bearer ${options.sessionToken}`);
  }
  if (options.cookieHeader) {
    headers.set("Cookie", options.cookieHeader);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });

  if (!response.ok) {
    throw new ApiError(await extractApiErrorMessage(response, path), response.status);
  }

  return (await response.json()) as T;
}

async function extractApiErrorMessage(response: Response, path: string): Promise<string> {
  const bodyText = await response.text().catch(() => "");
  let payload: { detail?: unknown; error?: unknown; message?: unknown } | null = null;
  if (bodyText) {
    try {
      payload = JSON.parse(bodyText) as { detail?: unknown; error?: unknown; message?: unknown };
    } catch {
      payload = null;
    }
  }

  const candidates = [payload?.detail, payload?.error, payload?.message];
  for (const candidate of candidates) {
    if (typeof candidate === "string" && candidate.trim()) {
      return candidate.trim();
    }
  }

  if (bodyText.trim()) {
    return bodyText.trim().slice(0, 400);
  }

  if (response.status >= 500 && path === "/api/crm/import/preview") {
    return "Brivoly hit an import hiccup while building the preview. It will keep trying best-effort recovery, so please retry the preview.";
  }

  return `Request failed with status ${response.status}.`;
}

function buildDashboardQuery(filters?: Partial<DashboardFilters>) {
  if (!filters) {
    return "";
  }

  const params = new URLSearchParams();
  if (filters.universe?.length) {
    filters.universe.forEach((symbol) => params.append("universe", symbol));
  }
  if (filters.benchmark) {
    params.set("benchmark", filters.benchmark);
  }
  if (filters.vix_symbol) {
    params.set("vix_symbol", filters.vix_symbol);
  }
  if (filters.risk_proxy) {
    params.set("risk_proxy", filters.risk_proxy);
  }
  if (filters.short_yield_symbol) {
    params.set("short_yield_symbol", filters.short_yield_symbol);
  }
  if (filters.long_yield_symbol) {
    params.set("long_yield_symbol", filters.long_yield_symbol);
  }
  if (typeof filters.lookback_years === "number") {
    params.set("lookback_years", String(filters.lookback_years));
  }

  const query = params.toString();
  return query ? `?${query}` : "";
}

export async function getSettingsBootstrap(): Promise<SettingsBootstrap> {
  return apiRequest<SettingsBootstrap>("/api/settings/bootstrap");
}

export async function getSession(options: ApiRequestOptions = {}): Promise<SessionResponse> {
  return apiRequest<SessionResponse>("/api/session", {}, options);
}

export async function getAccountSettings(options: ApiRequestOptions = {}): Promise<AccountSettings> {
  return apiRequest<AccountSettings>("/api/account/settings", {}, options);
}

export async function updateAccountSettings(
  payload: AccountSettings,
  options: ApiRequestOptions = {},
): Promise<AccountSettings> {
  return apiRequest<AccountSettings>(
    "/api/account/settings",
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
    options,
  );
}

export async function getAlertHistory(options: ApiRequestOptions = {}): Promise<AlertHistoryResponse> {
  return apiRequest<AlertHistoryResponse>("/api/alerts/history", {}, options);
}

export async function getBillingOverview(options: ApiRequestOptions = {}): Promise<BillingOverview> {
  return apiRequest<BillingOverview>("/api/account/billing", {}, options);
}

export async function getCrmFollowUpOverview(options: ApiRequestOptions = {}): Promise<CRMFollowUpOverview> {
  return apiRequest<CRMFollowUpOverview>("/api/crm/followups", {}, options);
}

export async function getCrmRemoteIntakeChannel(options: ApiRequestOptions = {}): Promise<CRMRemoteIntakeChannel> {
  return apiRequest<CRMRemoteIntakeChannel>("/api/crm/intake-channel", {}, options);
}

export async function updateCrmFollowUp(
  followUpId: string,
  payload: { action: "complete" | "snooze" | "note"; snooze_hours?: number; note_body?: string },
  options: ApiRequestOptions = {},
): Promise<CRMFollowUpOverview> {
  return apiRequest<CRMFollowUpOverview>(
    `/api/crm/followups/${followUpId}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
    options,
  );
}

export async function generateCrmFollowUpEmailDraft(
  followUpId: string,
  payload: {
    objective: "follow_up" | "recap" | "revive" | "close_loop";
    tone: "warm" | "direct" | "confident";
    length: "short" | "medium";
  },
  options: ApiRequestOptions = {},
): Promise<CRMEmailDraft> {
  return apiRequest<CRMEmailDraft>(
    `/api/crm/followups/${followUpId}/email-draft`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    options,
  );
}

export async function ingestCrmInboxThread(
  payload: {
    source?: string;
    thread_id: string;
    messages: Array<{
      message_id: string;
      sent_at: string;
      direction: "inbound" | "outbound";
      from_email: string;
      from_name?: string;
      to_emails: string[];
      subject?: string;
      body_text?: string;
      snippet?: string;
    }>;
  },
  options: ApiRequestOptions = {},
): Promise<CRMFollowUpOverview> {
  return apiRequest<CRMFollowUpOverview>(
    "/api/crm/inbox/threads",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    options,
  );
}

export async function previewCrmImport(
  payload: {
    source_type: "csv" | "excel" | "image" | "google_sheets";
    csv_content?: string;
    sheet_url?: string;
    file_name?: string;
    file_content_base64?: string;
    field_mapping?: Record<string, string | null>;
    clarification_answers?: Record<string, string>;
    row_overrides?: Record<string, Record<string, string>>;
  },
  options: ApiRequestOptions = {},
): Promise<CRMImportPreview> {
  return apiRequest<CRMImportPreview>(
    "/api/crm/import/preview",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    options,
  );
}

export async function commitCrmImport(
  payload: {
    source_type: "csv" | "excel" | "image" | "google_sheets";
    csv_content?: string;
    sheet_url?: string;
    file_name?: string;
    file_content_base64?: string;
    field_mapping?: Record<string, string | null>;
    clarification_answers?: Record<string, string>;
    row_overrides?: Record<string, Record<string, string>>;
  },
  options: ApiRequestOptions = {},
): Promise<CRMImportResult> {
  return apiRequest<CRMImportResult>(
    "/api/crm/import",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    options,
  );
}

export async function createBillingCheckoutSession(
  payload: { return_url?: string | null } = {},
  options: ApiRequestOptions = {},
): Promise<{ url: string }> {
  return apiRequest<{ url: string }>(
    "/api/account/billing/checkout",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    options,
  );
}

export async function createBillingPortalSession(
  payload: { return_url?: string | null } = {},
  options: ApiRequestOptions = {},
): Promise<{ url: string }> {
  return apiRequest<{ url: string }>(
    "/api/account/billing/portal",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    options,
  );
}

export async function getDashboard(options: DashboardRequestOptions = {}): Promise<DashboardSnapshot> {
  return apiRequest<DashboardSnapshot>(`/api/dashboard${buildDashboardQuery(options.filters)}`, {}, options);
}

export async function getShellData(options: ApiRequestOptions = {}): Promise<ShellData> {
  const errors: string[] = [];
  const bootstrap = await getSettingsBootstrap().catch((error: unknown) => {
    errors.push(extractErrorMessage(error, "Unable to load bootstrap settings."));
    return null;
  });

  const session = await getSession(options).catch((error: unknown) => {
    errors.push(extractErrorMessage(error, "Unable to load session state."));
    return null;
  });

  if (!session?.authenticated) {
    return {
      bootstrap,
      session,
      settings: null,
      alerts: null,
      billing: null,
      dashboard: null,
      errors,
    };
  }

  const [settings, alerts, billing, dashboard] = await Promise.all([
    getAccountSettings(options).catch((error: unknown) => {
      errors.push(extractErrorMessage(error, "Unable to load account settings."));
      return null;
    }),
    getAlertHistory(options).catch((error: unknown) => {
      errors.push(extractErrorMessage(error, "Unable to load alert history."));
      return null;
    }),
    getBillingOverview(options).catch((error: unknown) => {
      errors.push(extractErrorMessage(error, "Unable to load billing status."));
      return null;
    }),
    getDashboard(options).catch((error: unknown) => {
      errors.push(extractErrorMessage(error, "Unable to load dashboard snapshot."));
      return null;
    }),
  ]);

  return {
    bootstrap,
    session,
    settings,
    alerts,
    billing,
    dashboard,
    errors,
  };
}

function extractErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return fallback;
}
