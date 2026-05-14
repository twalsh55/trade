import type {
  AccountSettings,
  AlertHistoryResponse,
  DashboardFilters,
  DashboardSnapshot,
  SessionResponse,
  SettingsBootstrap,
  ShellData,
} from "@/lib/types";

const API_BASE_URL =
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
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(payload?.detail ?? `Request failed for ${path}`, response.status);
  }

  return (await response.json()) as T;
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
      dashboard: null,
      errors,
    };
  }

  const [settings, alerts, dashboard] = await Promise.all([
    getAccountSettings(options).catch((error: unknown) => {
      errors.push(extractErrorMessage(error, "Unable to load account settings."));
      return null;
    }),
    getAlertHistory(options).catch((error: unknown) => {
      errors.push(extractErrorMessage(error, "Unable to load alert history."));
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
