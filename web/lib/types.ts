export type AuthenticatedUser = {
  id: string;
  email: string | null;
  given_name: string | null;
  family_name: string | null;
  display_name: string | null;
  auth_provider: string;
  auth_issuer: string;
  auth_subject: string;
  created_at: string;
  updated_at: string;
  last_login_at: string;
};

export type SessionResponse = {
  authenticated: boolean;
  user: AuthenticatedUser | null;
};

export type SettingsBootstrap = {
  default_universe: string[];
  default_benchmark: string;
  default_vix_symbol: string;
  default_risk_proxy: string;
  default_short_yield_symbol: string;
  default_long_yield_symbol: string;
  default_lookback_years: number;
  app_base_url: string;
  clerk_publishable_key: string | null;
  clerk_frontend_api_host: string | null;
  clerk_sign_in_url: string | null;
  clerk_sign_up_url: string | null;
};

export type AccountSettings = {
  universe: string[];
  benchmark: string;
  vix_symbol: string;
  risk_proxy: string;
  short_yield_symbol: string;
  long_yield_symbol: string;
  lookback_years: number;
  telegram_enabled: boolean;
  business_name: string;
  business_website: string;
  outbound_sender_name: string;
  business_logo_data_url: string;
  onboarding_profile_deferred: boolean;
  crm_ai_prompt: string;
  crm_preferred_import_formats: string[];
  crm_image_intake_channels: string[];
  crm_image_intake_notes: string;
};

export type AlertHistoryEntry = {
  occurred_at: string;
  category: string;
  severity: string;
  title: string;
  message: string;
};

export type AlertHistoryResponse = {
  items: AlertHistoryEntry[];
  count: number;
};

export type BillingOverview = {
  enabled: boolean;
  customer_id: string | null;
  subscription_id: string | null;
  subscription_status: string | null;
  price_id: string | null;
  cancel_at_period_end: boolean;
  current_period_end: string | null;
  checkout_available: boolean;
  portal_available: boolean;
};

export type CRMLeadFollowUp = {
  id: string;
  lead_name: string;
  company_name: string;
  owner_name: string;
  stage: string;
  priority: string;
  contact_channel: string;
  last_contacted_at: string | null;
  next_follow_up_at: string;
  next_step: string;
  notes: string;
  timeline: CRMLeadTimelineEntry[];
};

export type CRMLeadTimelineEntry = {
  id: string;
  occurred_at: string;
  kind: string;
  channel: string;
  summary: string;
};

export type CRMFollowUpOverview = {
  generated_at: string;
  total_open: number;
  due_today: number;
  overdue: number;
  high_priority: number;
  items: CRMLeadFollowUp[];
};

export type CRMImportIssue = {
  row_number: number;
  severity: "error" | "warning";
  field: string | null;
  message: string;
};

export type CRMImportPreviewRow = {
  row_number: number;
  lead_name: string;
  company_name: string;
  owner_name: string;
  stage: string;
  next_follow_up_at: string | null;
  notes: string;
  duplicate: boolean;
  issues: CRMImportIssue[];
};

export type CRMImportHeaderMapping = {
  original_header: string;
  suggested_field: string | null;
  mapped_field: string | null;
};

export type CRMImportClarificationChoice = {
  value: string;
  label: string;
};

export type CRMImportClarificationQuestion = {
  id: string;
  prompt: string;
  choices: CRMImportClarificationChoice[];
};

export type CRMImportClarification = {
  assistant_message: string;
  required: boolean;
  questions: CRMImportClarificationQuestion[];
};

export type CRMImportPreview = {
  source_type: "csv" | "excel" | "image" | "google_sheets";
  source_label: string;
  normalized_headers: string[];
  header_mappings: CRMImportHeaderMapping[];
  available_fields: string[];
  total_rows: number;
  importable_rows: number;
  duplicate_rows: number;
  invalid_rows: number;
  rows: CRMImportPreviewRow[];
  issues: CRMImportIssue[];
  clarification: CRMImportClarification | null;
};

export type CRMImportResult = {
  imported_count: number;
  skipped_duplicates: number;
  skipped_invalid: number;
  overview: CRMFollowUpOverview;
};

export type CRMRemoteIntakeChannel = {
  telegram_available: boolean;
  intake_channel: string | null;
  intake_caption: string | null;
  instructions: string;
};

export type IndicatorPercentile = {
  name: string;
  current: number | null;
  p5: number | null;
  p50: number | null;
  p95: number | null;
};

export type PriceHistoryPoint = {
  date: string;
  price: number;
  ma50: number | null;
  ma200: number | null;
};

export type MarketBreadthPoint = {
  date: string;
  buyer_participation_20d: number | null;
  new_high_ratio_252: number | null;
};

export type DashboardSnapshot = {
  config: {
    universe: string[];
    benchmark: string;
    vix_symbol: string;
    risk_proxy: string;
    short_yield_symbol: string;
    long_yield_symbol: string;
    start_date: string;
    end_date: string;
  };
  refreshed_at: string;
  regime: string;
  risk_score: number;
  actions: string[];
  metrics: Record<string, number>;
  risk_components: Record<string, number>;
  indicator_percentiles: IndicatorPercentile[];
  price_history: PriceHistoryPoint[];
  market_breadth_history: MarketBreadthPoint[];
};

export type DashboardFilters = {
  universe: string[];
  benchmark: string;
  vix_symbol: string;
  risk_proxy: string;
  short_yield_symbol: string;
  long_yield_symbol: string;
  lookback_years: number;
};

export type ShellData = {
  bootstrap: SettingsBootstrap | null;
  session: SessionResponse | null;
  settings: AccountSettings | null;
  alerts: AlertHistoryResponse | null;
  billing: BillingOverview | null;
  dashboard: DashboardSnapshot | null;
  errors: string[];
};
