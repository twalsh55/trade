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

  json(response, 404, { detail: `No mock route for ${request.method} ${url.pathname}` });
});

server.listen(port, "127.0.0.1", () => {
  console.log(`Mock Trade API listening on http://127.0.0.1:${port}`);
});
