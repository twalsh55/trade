import http from "node:http";

const port = Number(process.argv[2] || "8001");
const validSessionToken = "test-session-token";

function json(response, status, payload) {
  response.writeHead(status, { "Content-Type": "application/json" });
  response.end(JSON.stringify(payload));
}

function readRequestBody(request) {
  return new Promise((resolve, reject) => {
    let body = "";
    request.on("data", (chunk) => {
      body += chunk;
    });
    request.on("end", () => {
      if (!body) {
        resolve(null);
        return;
      }
      try {
        resolve(JSON.parse(body));
      } catch (error) {
        reject(error);
      }
    });
    request.on("error", reject);
  });
}

function makeUser() {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    email: "ada@example.com",
    given_name: "Ada",
    family_name: "Lovelace",
    display_name: "Ada Lovelace",
    auth_provider: "clerk",
    auth_issuer: "https://example.clerk.accounts.dev",
    auth_subject: "user_123",
    created_at: "2024-05-06T12:30:00+00:00",
    updated_at: "2024-05-06T12:30:00+00:00",
    last_login_at: "2024-05-06T12:30:00+00:00",
  };
}

function makeState() {
  return {
    settings: {
      universe: ["SPY", "QQQ", "IWM", "EFA", "EEM"],
      benchmark: "SPY",
      vix_symbol: "^VIX",
      risk_proxy: "HYG",
      short_yield_symbol: "^IRX",
      long_yield_symbol: "^TNX",
      lookback_years: 4,
      telegram_enabled: false,
      crm_ai_prompt:
        "Focus on extracting follow-up-critical CRM fields from messy spreadsheets, files, and images. Prioritize lead name, company, owner, stage, next follow-up date, notes, and next step. Preserve evidence when uncertain.",
      crm_preferred_import_formats: ["csv", "google_sheets", "spreadsheet_screenshot"],
      crm_image_intake_channels: ["upload", "telegram"],
      crm_image_intake_notes: "Default to uploads inside Brivoly, then use Telegram for phone-captured note images.",
    },
    alertRequests: 0,
    alerts: [
      {
        occurred_at: "2024-05-06T12:30:00+00:00",
        category: "signal",
        severity: "info",
        title: "Baseline alert",
        message: "Initial alert history from the mock backend.",
      },
    ],
    crmFollowUps: [
      {
        id: "lead-amber-studio",
        lead_name: "Amber Flores",
        company_name: "Northstar Studio",
        owner_name: "Ada Lovelace",
        stage: "Discovery",
        priority: "high",
        contact_channel: "email",
        last_contacted_at: "2024-05-01T12:30:00+00:00",
        next_follow_up_at: "2024-05-06T08:30:00+00:00",
        next_step: "Send a concise recap and propose two call slots.",
        notes: "Interested, but waiting on a clearer summary of timeline and scope.",
        timeline: [
          {
            id: "amber-call",
            occurred_at: "2024-05-01T12:30:00+00:00",
            kind: "call",
            channel: "phone",
            summary: "Discovery call completed. Timing and scope were positive, but the recap needs to be tighter.",
          },
        ],
      },
    ],
  };
}

let state = makeState();

function isAuthenticated(request) {
  const authorization = request.headers.authorization || "";
  const [, token] = authorization.split(" ");
  return token === validSessionToken;
}

function buildDashboardSnapshot(benchmark, lookbackYears, universe) {
  return {
    config: {
      universe,
      benchmark,
      vix_symbol: state.settings.vix_symbol,
      risk_proxy: state.settings.risk_proxy,
      short_yield_symbol: state.settings.short_yield_symbol,
      long_yield_symbol: state.settings.long_yield_symbol,
      start_date: "2020-05-06",
      end_date: "2024-05-06",
    },
    refreshed_at: "2024-05-06T12:30:00+00:00",
    regime: benchmark === "QQQ" ? "Growth leadership" : "Constructive (Low Crash Stress)",
    risk_score: benchmark === "QQQ" ? 63.1 : 38.2,
    actions: [benchmark === "QQQ" ? "Trim exposure into volatility." : "Maintain strategic risk."],
    metrics: {
      price: benchmark === "QQQ" ? 402.5 : 359.0,
      ma50: 334.5,
      ma200: 259.5,
      drawdown_252: -0.04,
      vol20: 0.12,
      rsi14: 61.0,
      breadth_ratio: 0.82,
      yield_curve_spread: -1.1,
    },
    risk_components: {
      "Trend stress": benchmark === "QQQ" ? 44.5 : 10.0,
      "Yield curve stress": 80.0,
    },
    indicator_percentiles: [
      {
        name: "Price",
        current: benchmark === "QQQ" ? 402.5 : 359.0,
        p5: 110.0,
        p50: 220.0,
        p95: 350.0,
      },
    ],
    price_history: [
      { date: "2024-05-02", price: 350.0, ma50: 330.0, ma200: 260.0 },
      { date: "2024-05-03", price: 355.0, ma50: 332.0, ma200: 261.0 },
      { date: "2024-05-06", price: benchmark === "QQQ" ? 402.5 : 359.0, ma50: 334.5, ma200: 259.5 },
    ],
    market_breadth_history: [
      { date: "2024-05-02", buyer_participation_20d: 0.61, new_high_ratio_252: 0.24 },
      { date: "2024-05-03", buyer_participation_20d: 0.64, new_high_ratio_252: 0.27 },
      { date: "2024-05-06", buyer_participation_20d: 0.68, new_high_ratio_252: 0.32 },
    ],
  };
}

function buildCrmOverview() {
  const items = [...state.crmFollowUps].sort((a, b) => new Date(a.next_follow_up_at).getTime() - new Date(b.next_follow_up_at).getTime());
  return {
    generated_at: "2024-05-06T12:30:00+00:00",
    total_open: items.length,
    due_today: items.length,
    overdue: items.filter((item) => new Date(item.next_follow_up_at).getTime() < Date.parse("2024-05-06T12:30:00+00:00")).length,
    high_priority: items.filter((item) => item.priority === "high").length,
    items,
  };
}

const server = http.createServer(async (request, response) => {
  const url = new URL(request.url || "/", `http://${request.headers.host}`);

  if (url.pathname === "/__reset" && request.method === "POST") {
    state = makeState();
    json(response, 200, { ok: true });
    return;
  }

  if (url.pathname === "/api/settings/bootstrap" && request.method === "GET") {
    json(response, 200, {
      default_universe: state.settings.universe,
      default_benchmark: "SPY",
      default_vix_symbol: "^VIX",
      default_risk_proxy: "HYG",
      default_short_yield_symbol: "^IRX",
      default_long_yield_symbol: "^TNX",
      default_lookback_years: 4,
      app_base_url: "http://127.0.0.1:3001",
      clerk_publishable_key: null,
      clerk_frontend_api_host: null,
      clerk_sign_in_url: "https://example.clerk.accounts.dev/sign-in",
      clerk_sign_up_url: "https://example.clerk.accounts.dev/sign-up",
    });
    return;
  }

  if (url.pathname === "/api/session" && request.method === "GET") {
    if (!isAuthenticated(request)) {
      json(response, 200, { authenticated: false, user: null });
      return;
    }
    json(response, 200, { authenticated: true, user: makeUser() });
    return;
  }

  if (!isAuthenticated(request)) {
    json(response, 401, { detail: "Authentication required." });
    return;
  }

  if (url.pathname === "/api/account/settings" && request.method === "GET") {
    json(response, 200, state.settings);
    return;
  }

  if (url.pathname === "/api/account/billing" && request.method === "GET") {
    json(response, 200, {
      enabled: true,
      customer_id: "cus_mock_123",
      subscription_id: "sub_mock_123",
      subscription_status: "active",
      price_id: "price_mock_123",
      cancel_at_period_end: false,
      current_period_end: "2024-06-06T12:30:00+00:00",
      checkout_available: false,
      portal_available: true,
    });
    return;
  }

  if (url.pathname === "/api/account/billing/checkout" && request.method === "POST") {
    json(response, 200, { url: "https://checkout.stripe.test/session_mock_123" });
    return;
  }

  if (url.pathname === "/api/account/billing/portal" && request.method === "POST") {
    json(response, 200, { url: "https://billing.stripe.test/session_mock_123" });
    return;
  }

  if (url.pathname === "/api/account/settings" && request.method === "PUT") {
    const payload = await readRequestBody(request);
    state.settings = {
      ...state.settings,
      ...payload,
    };
    state.alerts.unshift({
      occurred_at: "2024-05-06T12:35:00+00:00",
      category: "settings",
      severity: "info",
      title: "Dashboard settings updated",
      message: `Defaults saved for benchmark ${state.settings.benchmark}.`,
    });
    json(response, 200, state.settings);
    return;
  }

  if (url.pathname === "/api/dashboard" && request.method === "GET") {
    const benchmark = url.searchParams.get("benchmark") || state.settings.benchmark;
    const universe = url.searchParams.getAll("universe");
    const lookbackYears = Number(url.searchParams.get("lookback_years") || state.settings.lookback_years);
    json(response, 200, buildDashboardSnapshot(benchmark, lookbackYears, universe.length ? universe : state.settings.universe));
    return;
  }

  if (url.pathname === "/api/alerts/history" && request.method === "GET") {
    state.alertRequests += 1;
    const items =
      state.alertRequests > 1
        ? [
            {
              occurred_at: "2024-05-06T12:40:00+00:00",
              category: "signal",
              severity: "warning",
              title: "Refreshed alert feed",
              message: "The alert refresh route returned fresh mock data.",
            },
            ...state.alerts,
          ]
        : state.alerts;
    json(response, 200, { items, count: items.length });
    return;
  }

  if (url.pathname === "/api/crm/followups" && request.method === "GET") {
    json(response, 200, buildCrmOverview());
    return;
  }

  if (url.pathname.startsWith("/api/crm/followups/") && request.method === "PATCH") {
    const followUpId = url.pathname.split("/").pop();
    const payload = await readRequestBody(request);
    const index = state.crmFollowUps.findIndex((item) => item.id === followUpId);
    if (index === -1) {
      json(response, 404, { detail: "CRM follow-up not found." });
      return;
    }

    if (payload.action === "complete") {
      state.crmFollowUps.splice(index, 1);
    } else if (payload.action === "snooze") {
      state.crmFollowUps[index].next_follow_up_at = "2024-05-07T12:30:00+00:00";
    } else if (payload.action === "note") {
      state.crmFollowUps[index].notes = payload.note_body;
      state.crmFollowUps[index].timeline.unshift({
        id: `${followUpId}-note`,
        occurred_at: "2024-05-06T12:30:00+00:00",
        kind: "internal_note",
        channel: "internal",
        summary: payload.note_body,
      });
    }

    json(response, 200, buildCrmOverview());
    return;
  }

  if (url.pathname === "/api/crm/import/preview" && request.method === "POST") {
    json(response, 200, {
      source_type: "csv",
      source_label: "CSV upload",
      normalized_headers: ["lead_name", "company_name", "owner_name", "stage", "next_follow_up_at", "notes"],
      header_mappings: [
        { original_header: "contact", suggested_field: "lead_name", mapped_field: "lead_name" },
        { original_header: "company", suggested_field: "company_name", mapped_field: "company_name" },
        { original_header: "owner", suggested_field: "owner_name", mapped_field: "owner_name" },
        { original_header: "status", suggested_field: "stage", mapped_field: "stage" },
        { original_header: "next follow-up", suggested_field: "next_follow_up_at", mapped_field: "next_follow_up_at" },
        { original_header: "notes", suggested_field: "notes", mapped_field: "notes" },
      ],
      available_fields: [
        "lead_name",
        "company_name",
        "owner_name",
        "stage",
        "next_follow_up_at",
        "notes",
        "priority",
        "contact_channel",
        "next_step",
      ],
      total_rows: 2,
      importable_rows: 1,
      duplicate_rows: 1,
      invalid_rows: 0,
      issues: [
        {
          row_number: 3,
          severity: "warning",
          field: null,
          message: "This lead already exists in the current CRM queue and will be skipped.",
        },
      ],
      rows: [
        {
          row_number: 2,
          lead_name: "Taylor Brooks",
          company_name: "Beacon Ridge",
          owner_name: "Samir Patel",
          stage: "Qualification",
          next_follow_up_at: "2024-05-09T09:00:00+00:00",
          notes: "Imported from the founder's sheet.",
          duplicate: false,
          issues: [],
        },
        {
          row_number: 3,
          lead_name: "Amber Flores",
          company_name: "Northstar Studio",
          owner_name: "Ada Lovelace",
          stage: "Discovery",
          next_follow_up_at: "2024-05-10T09:00:00+00:00",
          notes: "Duplicate row.",
          duplicate: true,
          issues: [
            {
              row_number: 3,
              severity: "warning",
              field: null,
              message: "This lead already exists in the current CRM queue and will be skipped.",
            },
          ],
        },
      ],
    });
    return;
  }

  if (url.pathname === "/api/crm/import" && request.method === "POST") {
    state.crmFollowUps.unshift({
      id: "lead-import-beacon-ridge",
      lead_name: "Taylor Brooks",
      company_name: "Beacon Ridge",
      owner_name: "Samir Patel",
      stage: "Qualification",
      priority: "medium",
      contact_channel: "spreadsheet",
      last_contacted_at: null,
      next_follow_up_at: "2024-05-09T09:00:00+00:00",
      next_step: "Samir Patel to send the next follow-up and confirm the current qualification status.",
      notes: "Imported from the founder's sheet.",
      timeline: [
        {
          id: "beacon-ridge-import",
          occurred_at: "2024-05-06T12:30:00+00:00",
          kind: "import",
          channel: "csv_upload",
          summary: "Imported from CSV upload. Owner: Samir Patel. Stage: Qualification.",
        },
      ],
    });
    json(response, 200, {
      imported_count: 1,
      skipped_duplicates: 1,
      skipped_invalid: 0,
      overview: buildCrmOverview(),
    });
    return;
  }

  json(response, 404, { detail: `No mock route for ${request.method} ${url.pathname}` });
});

server.listen(port, "127.0.0.1", () => {
  console.log(`Mock Brivoly API listening on http://127.0.0.1:${port}`);
});
