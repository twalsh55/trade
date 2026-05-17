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
  profile_alias: string;
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
  email_address: string;
  stage: string;
  priority: string;
  contact_channel: string;
  last_contacted_at: string | null;
  next_follow_up_at: string;
  next_step: string;
  notes: string;
  timeline: CRMLeadTimelineEntry[];
  referral_source_name: string;
  birthday: string | null;
  company_milestone_name: string;
  company_milestone_date: string | null;
  last_meaningful_interaction_at: string | null;
  relationship_health_score: number;
  relationship_health_label: "healthy" | "watch" | "at_risk" | string;
  relationship_state: "active" | "warm" | "drifting" | "stale" | "at_risk" | string;
  relationship_timing_nudge: string;
  relationship_context_summary: string;
  relationship_recent_changes_summary: string;
  relationship_recent_upload_summary: string;
  relationship_upload_follow_through_hint: string;
  relationship_last_30_days_summary: string;
  relationship_meeting_prep_summary: string;
  relationship_reconnect_why_now: string;
  relationship_reconnect_next_move: string;
  relationship_reconnect_message_hint: string;
  dormant: boolean;
  relationship_reminders: CRMRelationshipReminder[];
  recent_email_threads: CRMEmailThreadSummary[];
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
  relationship_summary: CRMRelationshipSummary | null;
  pipeline_summary: CRMPipelineSummary | null;
  inbox_summary: CRMInboxSummary | null;
};

export type CRMEmailThreadSummary = {
  thread_id: string;
  subject: string;
  counterpart_name: string;
  counterpart_email: string;
  last_message_at: string;
  last_message_direction: "inbound" | "outbound" | string;
  message_count: number;
  snippet: string;
  needs_reply: boolean;
  waiting_on_contact: boolean;
  memory_summary: string;
  next_touch_hint: string;
  open_loop: string;
  relationship_pulse: string;
  continuity_span: string;
  recent_change_hint: string;
  carry_forward_hint: string;
  unresolved_hint: string;
  continuity_memory: string;
};

export type CRMRelationshipReminder = {
  kind: "referral" | "birthday" | "company_milestone" | string;
  title: string;
  message: string;
  due_at: string | null;
};

export type CRMWarmIntroConnection = {
  source_name: string;
  target_lead_id: string;
  target_lead_name: string;
  target_company_name: string;
  owner_name: string;
};

export type CRMRelationshipSummary = {
  active_count: number;
  warm_count: number;
  drifting_count: number;
  stale_count: number;
  at_risk_count: number;
  referral_reminder_count: number;
  milestone_reminder_count: number;
  warm_intro_connections: CRMWarmIntroConnection[];
};

export type CRMPipelineStageSummary = {
  stage: string;
  lead_count: number;
  overdue_count: number;
  due_this_week_count: number;
  high_priority_count: number;
  dormant_count: number;
};

export type CRMPipelineSummary = {
  stage_summaries: CRMPipelineStageSummary[];
};

export type CRMInboxSummary = {
  connected_contact_count: number;
  active_thread_count: number;
  needs_reply_count: number;
  waiting_on_contact_count: number;
  stale_thread_count: number;
  auto_created_contact_count: number;
};

export type CRMEmailDraft = {
  follow_up_id: string;
  objective: "follow_up" | "recap" | "revive" | "close_loop";
  tone: "warm" | "direct" | "confident";
  length: "short" | "medium";
  subject: string;
  body: string;
  rationale: string[];
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
  priority: string;
  contact_channel: string;
  next_follow_up_at: string | null;
  next_step: string;
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
  magic_link_url: string | null;
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
