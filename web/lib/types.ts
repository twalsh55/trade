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
