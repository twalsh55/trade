from __future__ import annotations

import logging
import os
from pathlib import Path
from datetime import date, datetime, timedelta
from functools import lru_cache
from base64 import b64encode
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
from psycopg import OperationalError
import streamlit as st
import streamlit.components.v2 as components_v2
from streamlit.errors import StreamlitSecretNotFoundError
from streamlit_autorefresh import st_autorefresh

from src.adapters.auth.clerk_auth import AuthenticationError, ClerkAuthConfig, ClerkAuthProvider
from src.adapters.notifications.telegram_notifier import TelegramNotificationError, TelegramNotifier
from src.adapters.persistence.postgres_user_repository import PostgresUserRepository
from src.application.auth import AuthenticateUserUseCase
from src.adapters.market_data.yfinance_provider import YFinanceMarketDataAdapter
from src.application.use_cases import BuildCrashDashboardUseCase
from src.domain.auth import User
from src.domain.models import CAUTION_CUTOFF, DEFAULT_UNIVERSE, RISK_OFF_CUTOFF, DashboardConfig
from src.domain.services import compute_buyer_participation_series, compute_new_high_ratio_series

REFRESH_INTERVAL_SECONDS = 300
LAST_ALERT_SIGNATURE_KEY = "last_telegram_alert_signature"
STARTUP_MESSAGE_SENT_KEY = "startup_telegram_message_sent"
TELEGRAM_STATUS_KEY = "telegram_status_message"
AUTH_ERROR_KEY = "auth_error_message"
DISPLAY_TIMEZONE = ZoneInfo(os.getenv("APP_TIMEZONE", "Europe/Rome"))
CLERK_SESSION_COOKIE = "__session"
CLERK_SESSION_TOKEN_PARAM = "clerk_session_token"

logger = logging.getLogger(__name__)

BROVOLY_AUTH_PANEL_HTML = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=Space+Grotesk:wght@500;700&display=swap');

  :root {
    --brovoly-electric: #1650ff;
    --brovoly-deep: #0d1b55;
    --brovoly-deeper: #07122f;
    --brovoly-glow: #25d0c6;
    --brovoly-mist: rgba(255, 255, 255, 0.08);
    --brovoly-line: rgba(255, 255, 255, 0.12);
    --brovoly-copy: rgba(231, 238, 248, 0.84);
  }

  * { box-sizing: border-box; }

  .brovoly-stage {
    width: 100%;
    max-width: 1120px;
    margin: 0 auto 14px;
    color: white;
    font-family: "IBM Plex Sans", "Avenir Next", sans-serif;
  }

  .brovoly-wrap {
    padding: 30px;
    border-radius: 30px;
    overflow: hidden;
    border: 1px solid var(--brovoly-line);
    position: relative;
    background:
      radial-gradient(circle at top left, rgba(37, 208, 198, 0.16), transparent 28%),
      radial-gradient(circle at 85% 18%, rgba(22, 80, 255, 0.22), transparent 24%),
      linear-gradient(145deg, var(--brovoly-deep), var(--brovoly-deeper));
    box-shadow: 0 36px 80px rgba(8, 20, 38, 0.24);
  }

  .brovoly-wrap::before {
    content: "";
    position: absolute;
    inset: 0;
    background:
      linear-gradient(115deg, rgba(255, 255, 255, 0.04), transparent 38%),
      radial-gradient(circle at 100% 100%, rgba(37, 208, 198, 0.16), transparent 34%);
    pointer-events: none;
  }

  .brovoly-main {
    display: grid;
    grid-template-columns: minmax(0, 1.15fr) minmax(280px, 0.85fr);
    gap: 28px;
    align-items: stretch;
    position: relative;
    z-index: 1;
  }

  .brovoly-top {
    display: grid;
    grid-template-columns: 92px 1fr;
    gap: 20px;
    align-items: center;
  }

  .brovoly-mark {
    width: 92px;
    height: 92px;
    border-radius: 24px;
    display: grid;
    place-items: center;
    background: linear-gradient(160deg, rgba(22, 80, 255, 0.98), rgba(37, 208, 198, 0.72));
    box-shadow: 0 22px 44px rgba(8, 20, 38, 0.36);
  }

  .brovoly-eyebrow {
    margin-bottom: 8px;
    color: rgba(37, 208, 198, 0.96);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.28em;
    text-transform: uppercase;
  }

  .brovoly-name {
    margin: 0;
    font-family: "Space Grotesk", "IBM Plex Sans", sans-serif;
    font-size: 40px;
    line-height: 0.95;
    letter-spacing: -0.04em;
  }

  .brovoly-copy {
    margin: 10px 0 0;
    max-width: 560px;
    color: var(--brovoly-copy);
    font-size: 15px;
    line-height: 1.6;
  }

  .brovoly-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
    margin-top: 22px;
  }

  .brovoly-card {
    border-radius: 18px;
    padding: 14px 16px;
    background: var(--brovoly-mist);
    border: 1px solid rgba(255, 255, 255, 0.08);
    backdrop-filter: blur(8px);
  }

  .brovoly-card-label {
    color: rgba(37, 208, 198, 0.96);
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.22em;
    text-transform: uppercase;
  }

  .brovoly-card-copy {
    margin-top: 6px;
    color: rgba(244, 247, 251, 0.86);
    font-size: 13px;
    line-height: 1.5;
  }

  .brovoly-graphic {
    position: relative;
    min-height: 280px;
    border-radius: 24px;
    padding: 20px;
    border: 1px solid rgba(255, 255, 255, 0.08);
    background:
      linear-gradient(180deg, rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0.02)),
      radial-gradient(circle at top right, rgba(22, 80, 255, 0.18), transparent 32%);
    overflow: hidden;
  }

  .brovoly-graphic::before {
    content: "";
    position: absolute;
    inset: -25% auto auto 62%;
    width: 180px;
    height: 180px;
    border-radius: 999px;
    background: radial-gradient(circle, rgba(37, 208, 198, 0.16), transparent 68%);
    pointer-events: none;
  }

  .brovoly-badge {
    position: absolute;
    top: 16px;
    left: 16px;
    z-index: 2;
    padding: 7px 10px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.08);
    color: rgba(37, 208, 198, 0.96);
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.22em;
    text-transform: uppercase;
  }

  .brovoly-orbit {
    position: absolute;
    inset: 0;
  }

  .brovoly-orbit svg {
    position: absolute;
    inset: auto;
  }

  .brovoly-orbit svg:nth-child(1) {
    top: 30px;
    right: 18px;
    opacity: 0.18;
    transform: scale(1.35);
  }

  .brovoly-orbit svg:nth-child(2) {
    top: 92px;
    left: 26px;
    opacity: 0.12;
    transform: scale(1.08);
  }

  .brovoly-orbit svg:nth-child(3) {
    bottom: 24px;
    right: 44px;
    opacity: 0.2;
    transform: scale(0.84);
  }

  .brovoly-logo-card {
    position: absolute;
    inset: 56px 26px auto 34px;
    z-index: 2;
    padding: 18px;
    border-radius: 24px;
    background: rgba(255, 255, 255, 0.94);
    box-shadow: 0 28px 50px rgba(6, 14, 36, 0.28);
  }

  .brovoly-logo-card img {
    display: block;
    width: min(100%, 240px);
    height: auto;
  }

  .brovoly-pulse {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    height: 132px;
    padding: 0 10px 8px;
  }

  .brovoly-pulse svg {
    width: 100%;
    height: 100%;
  }

  .brovoly-brief {
    position: absolute;
    right: 18px;
    top: 138px;
    z-index: 2;
    width: 170px;
    padding: 14px 14px 12px;
    border-radius: 18px;
    background: rgba(6, 15, 28, 0.5);
    border: 1px solid rgba(255, 255, 255, 0.08);
    backdrop-filter: blur(8px);
  }

  .brovoly-brief-label {
    color: rgba(37, 208, 198, 0.95);
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.18em;
    text-transform: uppercase;
  }

  .brovoly-brief-copy {
    margin-top: 7px;
    color: rgba(235, 241, 250, 0.82);
    font-size: 12px;
    line-height: 1.55;
  }

  @media (max-width: 860px) {
    .brovoly-main { grid-template-columns: 1fr; }
    .brovoly-graphic { min-height: 240px; }
  }

  @media (max-width: 720px) {
    .brovoly-wrap { padding: 22px; }
    .brovoly-top { grid-template-columns: 1fr; }
    .brovoly-name { font-size: 34px; }
    .brovoly-grid { grid-template-columns: 1fr; }
    .brovoly-brief { position: static; width: 100%; margin-top: 16px; }
    .brovoly-logo-card { position: static; margin-bottom: 18px; }
  }
</style>

<section class="brovoly-stage">
  <div class="brovoly-wrap">
    <div class="brovoly-main">
      <div>
        <div class="brovoly-top">
          <div class="brovoly-mark" aria-hidden="true">
            <svg width="54" height="54" viewBox="0 0 54 54" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M17 10H28.5C35.4036 10 41 15.5964 41 22.5C41 26.6099 39.0209 30.2574 35.9634 32.5368L41.5 44H31.5L27.5 35H17V44H9V10H17Z" fill="#F8FAFC"/>
              <path d="M17 18V27H28.5C30.9853 27 33 24.9853 33 22.5C33 20.0147 30.9853 18 28.5 18H17Z" fill="#0D1B55"/>
              <circle cx="42.5" cy="40.5" r="4.5" fill="#25D0C6"/>
            </svg>
          </div>
          <div>
            <div class="brovoly-eyebrow">Brivoly Access</div>
            <h1 class="brovoly-name">BRIVOLY</h1>
            <p class="brovoly-copy">
              Secure entry to your market intelligence workspace, built for disciplined monitoring,
              fast alerting, and a cleaner operational view of risk.
            </p>
          </div>
        </div>

        <div class="brovoly-grid">
          <div class="brovoly-card">
            <div class="brovoly-card-label">Protected</div>
            <div class="brovoly-card-copy">Authentication is routed through Clerk while Brivoly keeps its own internal user records.</div>
          </div>
          <div class="brovoly-card">
            <div class="brovoly-card-label">Focused</div>
            <div class="brovoly-card-copy">Designed for traders and operators who want one reliable place for dashboard access and signal review.</div>
          </div>
          <div class="brovoly-card">
            <div class="brovoly-card-label">Portable</div>
            <div class="brovoly-card-copy">The app boundary stays provider-agnostic, making future identity migrations much easier.</div>
          </div>
        </div>
      </div>

      <div class="brovoly-graphic" aria-hidden="true">
        <div class="brovoly-badge">Brand signal</div>
        <div class="brovoly-logo-card">{{BRIVOLY_LOGO_TEXT_IMAGE}}</div>
        <div class="brovoly-orbit">
          <svg width="120" height="120" viewBox="0 0 54 54" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M17 10H28.5C35.4036 10 41 15.5964 41 22.5C41 26.6099 39.0209 30.2574 35.9634 32.5368L41.5 44H31.5L27.5 35H17V44H9V10H17Z" stroke="rgba(22,80,255,0.95)" stroke-width="1.6"/>
            <path d="M17 18V27H28.5C30.9853 27 33 24.9853 33 22.5C33 20.0147 30.9853 18 28.5 18H17Z" stroke="rgba(255,255,255,0.82)" stroke-width="1.4"/>
            <circle cx="42.5" cy="40.5" r="4.5" fill="rgba(37,208,198,0.95)"/>
          </svg>
          <svg width="92" height="92" viewBox="0 0 54 54" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M17 10H28.5C35.4036 10 41 15.5964 41 22.5C41 26.6099 39.0209 30.2574 35.9634 32.5368L41.5 44H31.5L27.5 35H17V44H9V10H17Z" stroke="rgba(255,255,255,0.72)" stroke-width="1.6"/>
            <path d="M17 18V27H28.5C30.9853 27 33 24.9853 33 22.5C33 20.0147 30.9853 18 28.5 18H17Z" stroke="rgba(37,208,198,0.9)" stroke-width="1.4"/>
            <circle cx="42.5" cy="40.5" r="4.5" fill="rgba(37,208,198,0.95)"/>
          </svg>
          <svg width="84" height="84" viewBox="0 0 54 54" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M17 10H28.5C35.4036 10 41 15.5964 41 22.5C41 26.6099 39.0209 30.2574 35.9634 32.5368L41.5 44H31.5L27.5 35H17V44H9V10H17Z" fill="rgba(22,80,255,0.9)"/>
            <path d="M17 18V27H28.5C30.9853 27 33 24.9853 33 22.5C33 20.0147 30.9853 18 28.5 18H17Z" fill="rgba(8,20,38,0.86)"/>
            <circle cx="42.5" cy="40.5" r="4.5" fill="rgba(37,208,198,0.95)"/>
          </svg>
        </div>
        <div class="brovoly-brief">
          <div class="brovoly-brief-label">Logo language</div>
          <div class="brovoly-brief-copy">
            The presentation graphics echo the Brivoly mark with electric-blue curves,
            the aqua accent dot, and a measured market pulse.
          </div>
        </div>
        <div class="brovoly-pulse">
          <svg viewBox="0 0 420 132" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M10 110C52 104 78 70 118 70C160 70 176 98 210 98C246 98 262 42 300 42C334 42 356 76 410 62" stroke="rgba(255,255,255,0.16)" stroke-width="2"/>
            <path d="M10 110C52 104 78 70 118 70C160 70 176 98 210 98C246 98 262 42 300 42C334 42 356 76 410 62" stroke="url(#brovolyPulse)" stroke-width="4" stroke-linecap="round"/>
            <circle cx="300" cy="42" r="7" fill="#25D0C6"/>
            <circle cx="300" cy="42" r="18" fill="rgba(37,208,198,0.14)"/>
            <defs>
              <linearGradient id="brovolyPulse" x1="10" y1="110" x2="410" y2="42" gradientUnits="userSpaceOnUse">
                <stop stop-color="rgba(255,255,255,0.22)"/>
                <stop offset="0.45" stop-color="#1650FF"/>
                <stop offset="0.75" stop-color="#25D0C6"/>
                <stop offset="1" stop-color="#7DD3FC"/>
              </linearGradient>
            </defs>
          </svg>
        </div>
      </div>
    </div>
  </div>
</section>
"""

CLERK_AUTH_BRIDGE_HTML = """
<div class="brovoly-auth-shell">
  <div class="brovoly-auth-frame">
    <div class="brovoly-auth-label">Secure sign-in</div>
    <div id="clerk-auth-root" style="min-height: 420px;"></div>
    <p id="clerk-auth-status" class="brovoly-auth-status">Loading sign-in...</p>
  </div>
</div>
"""

CLERK_AUTH_BRIDGE_CSS = """
.brovoly-auth-shell {
  width: 100%;
  max-width: 720px;
  margin: 12px auto 0;
}

.brovoly-auth-frame {
  border-radius: 26px;
  padding: 24px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.92)),
    radial-gradient(circle at top right, rgba(246, 193, 119, 0.12), transparent 30%);
  box-shadow: 0 28px 68px rgba(15, 23, 42, 0.14);
  border: 1px solid rgba(148, 163, 184, 0.22);
}

.brovoly-auth-label {
  margin-bottom: 16px;
  color: #9a6c1c;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.22em;
  text-transform: uppercase;
}

.brovoly-auth-status {
  margin: 0.75rem 0 0;
  color: #475569;
  font: 14px/1.5 "IBM Plex Sans", "Avenir Next", sans-serif;
}
"""

CLERK_ACCOUNT_WIDGET_HTML = """
<div class="brivoly-account-shell">
  <div id="clerk-user-button"></div>
  <button id="clerk-sign-out" class="brivoly-sign-out">Sign out</button>
</div>
"""

CLERK_ACCOUNT_WIDGET_CSS = """
.brivoly-account-shell {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.brivoly-sign-out {
  border: 1px solid #d1d5db;
  background: white;
  border-radius: 999px;
  padding: 0.45rem 0.85rem;
  cursor: pointer;
  font: 500 14px/1 "IBM Plex Sans", "Avenir Next", sans-serif;
}
"""

HTML_BLOCK_COMPONENT_HTML = """
<div id="trade-html-block-root"></div>
"""

HTML_BLOCK_COMPONENT_JS = """
export default function(component) {
  const { data, parentElement } = component
  const root = parentElement.querySelector('#trade-html-block-root')
  if (!root) {
    return
  }

  root.innerHTML = data.html || ''
}
"""

CLERK_ACCOUNT_WIDGET_JS = """
function loadScript(src, attributes = {}) {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[data-trade-src="${src}"]`)
    if (existing) {
      if (existing.dataset.loaded === 'true') {
        resolve()
        return
      }
      existing.addEventListener('load', () => resolve(), { once: true })
      existing.addEventListener('error', () => reject(new Error(`Failed to load ${src}`)), { once: true })
      return
    }

    const script = document.createElement('script')
    script.src = src
    script.async = true
    script.dataset.tradeSrc = src
    Object.entries(attributes).forEach(([key, value]) => {
      script.setAttribute(key, value)
    })
    script.addEventListener('load', () => {
      script.dataset.loaded = 'true'
      resolve()
    }, { once: true })
    script.addEventListener('error', () => reject(new Error(`Failed to load ${src}`)), { once: true })
    document.head.appendChild(script)
  })
}

async function ensureClerk(publishableKey, host) {
  if (!window.__tradeClerkLoadPromise) {
    window.__tradeClerkLoadPromise = (async () => {
      await loadScript(`https://${host}/npm/@clerk/clerk-js@6/dist/clerk.browser.js`, {
        crossorigin: 'anonymous',
        'data-clerk-publishable-key': publishableKey,
      })
      await loadScript(`https://${host}/npm/@clerk/ui@1/dist/ui.browser.js`, {
        crossorigin: 'anonymous',
      })
      await window.Clerk.load({
        ui: { ClerkUI: window.__internal_ClerkUICtor },
      })
      return window.Clerk
    })()
  }
  return window.__tradeClerkLoadPromise
}

export default function(component) {
  const { data, parentElement } = component
  let cancelled = false

  async function init() {
    try {
      const clerk = await ensureClerk(data.publishableKey, data.host)
      if (cancelled) {
        return
      }

      if (!clerk.isSignedIn) {
        window.location.reload()
        return
      }

      const mountTarget = parentElement.querySelector('#clerk-user-button')
      const signOutButton = parentElement.querySelector('#clerk-sign-out')
      mountTarget.replaceChildren()
      clerk.mountUserButton(mountTarget)
      signOutButton.onclick = async () => {
        await clerk.signOut()
        window.location.reload()
      }
    } catch (error) {
      console.error(error)
    }
  }

  init()

  return () => {
    cancelled = true
  }
}
"""

BRIVOLY_LOGO_IMAGE_PLACEHOLDER = "{{BRIVOLY_LOGO_IMAGE}}"
BRIVOLY_LOGO_TEXT_IMAGE_PLACEHOLDER = "{{BRIVOLY_LOGO_TEXT_IMAGE}}"

CLERK_AUTH_BRIDGE_JS = """
function loadScript(src, attributes = {}) {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[data-trade-src="${src}"]`)
    if (existing) {
      if (existing.dataset.loaded === 'true') {
        resolve()
        return
      }
      existing.addEventListener('load', () => resolve(), { once: true })
      existing.addEventListener('error', () => reject(new Error(`Failed to load ${src}`)), { once: true })
      return
    }

    const script = document.createElement('script')
    script.src = src
    script.async = true
    script.dataset.tradeSrc = src
    Object.entries(attributes).forEach(([key, value]) => {
      script.setAttribute(key, value)
    })
    script.addEventListener('load', () => {
      script.dataset.loaded = 'true'
      resolve()
    }, { once: true })
    script.addEventListener('error', () => reject(new Error(`Failed to load ${src}`)), { once: true })
    document.head.appendChild(script)
  })
}

async function ensureClerk(publishableKey, host) {
  if (!window.__tradeClerkLoadPromise) {
    window.__tradeClerkLoadPromise = (async () => {
      await loadScript(`https://${host}/npm/@clerk/clerk-js@6/dist/clerk.browser.js`, {
        crossorigin: 'anonymous',
        'data-clerk-publishable-key': publishableKey,
      })
      await loadScript(`https://${host}/npm/@clerk/ui@1/dist/ui.browser.js`, {
        crossorigin: 'anonymous',
      })
      await window.Clerk.load({
        ui: { ClerkUI: window.__internal_ClerkUICtor },
      })
      return window.Clerk
    })()
  }
  return window.__tradeClerkLoadPromise
}

export default function(component) {
  const { data, parentElement, setTriggerValue } = component
  const rootNode = parentElement.querySelector('#clerk-auth-root')
  const statusNode = parentElement.querySelector('#clerk-auth-status')
  let cancelled = false

  function setStatus(message) {
    if (statusNode) {
      statusNode.textContent = message
    }
  }

  async function init() {
    try {
      setStatus('Loading sign-in...')
      const clerk = await ensureClerk(data.publishableKey, data.host)
      if (cancelled) {
        return
      }

      if (clerk.isSignedIn && clerk.session) {
        if (data.authError) {
          setStatus('Signed in with Clerk. Fix the app error above, then refresh this page.')
          return
        }

        const token = await clerk.session.getToken({ skipCache: true })
        if (cancelled) {
          return
        }

        if (token) {
          setStatus('Signed in. Finalizing...')
          setTriggerValue('session_token', token)
          return
        }

        setStatus('Clerk session found, but no session token was returned.')
        return
      }

      rootNode.replaceChildren()
      clerk.mountSignIn(rootNode)
      setStatus('')
    } catch (error) {
      console.error(error)
      setStatus('Unable to load the Clerk sign-in widget. Check the browser console for details.')
    }
  }

  init()

  return () => {
    cancelled = true
  }
}
"""


def get_session_state() -> dict[str, object]:
    session_state = getattr(st, "session_state", None)
    if isinstance(session_state, dict):
        return session_state
    return {}


def get_query_params() -> object:
    return getattr(st, "query_params", {})


def get_query_param(name: str) -> str | None:
    query_params = get_query_params()
    value = getattr(query_params, "get", lambda _name, _default=None: _default)(name, None)
    if isinstance(value, list):
        value = value[0] if value else None
    return str(value) if value else None


def clear_query_param(name: str) -> None:
    query_params = get_query_params()
    pop = getattr(query_params, "pop", None)
    if callable(pop):
        pop(name, None)


def get_request_cookie(name: str) -> str | None:
    context = getattr(st, "context", None)
    cookies = getattr(context, "cookies", None)
    if cookies is None:
        return None
    value = cookies.get(name)
    return str(value) if value else None


def get_image_data_uri(path: str) -> str | None:
    logo_path = Path(path)
    if not logo_path.exists():
        return None
    return f"data:image/png;base64,{b64encode(logo_path.read_bytes()).decode('ascii')}"


def build_brivoly_auth_panel_html() -> str:
    logo_data_uri = get_image_data_uri("logo.png")
    logo_text_data_uri = get_image_data_uri("logo_text.png")
    if logo_data_uri:
        logo_markup = f'<img src="{logo_data_uri}" alt="Brivoly symbol" />'
    else:
        logo_markup = (
            '<div style="font: 700 28px/1 \\"Space Grotesk\\", sans-serif; color: #0d1b55;">'
            'Brivoly</div>'
        )
    if logo_text_data_uri:
        logo_text_markup = f'<img src="{logo_text_data_uri}" alt="Brivoly logo" />'
    else:
        logo_text_markup = logo_markup

    return (
        BROVOLY_AUTH_PANEL_HTML
        .replace(BRIVOLY_LOGO_IMAGE_PLACEHOLDER, logo_markup)
        .replace(BRIVOLY_LOGO_TEXT_IMAGE_PLACEHOLDER, logo_text_markup)
    )

def render_brivoly_auth_panel() -> None:
    get_html_block_renderer()(
        data={"html": build_brivoly_auth_panel_html()},
        key="brivoly_auth_panel",
    )


@lru_cache(maxsize=1)
def get_html_block_renderer():
    return components_v2.component(
        "trade_html_block",
        html=HTML_BLOCK_COMPONENT_HTML,
        js=HTML_BLOCK_COMPONENT_JS,
        isolate_styles=False,
    )


@lru_cache(maxsize=1)
def get_clerk_auth_bridge():
    return components_v2.component(
        "clerk_auth_bridge",
        html=CLERK_AUTH_BRIDGE_HTML,
        js=CLERK_AUTH_BRIDGE_JS,
        css=CLERK_AUTH_BRIDGE_CSS,
        isolate_styles=False,
    )


@lru_cache(maxsize=1)
def get_clerk_account_widget():
    return components_v2.component(
        "clerk_account_widget",
        html=CLERK_ACCOUNT_WIDGET_HTML,
        css=CLERK_ACCOUNT_WIDGET_CSS,
        js=CLERK_ACCOUNT_WIDGET_JS,
        isolate_styles=False,
    )


@lru_cache(maxsize=1)
def build_authenticate_user_use_case() -> AuthenticateUserUseCase:
    publishable_key = os.getenv("CLERK_PUBLISHABLE_KEY")
    secret_key = os.getenv("CLERK_SECRET_KEY")
    database_url = os.getenv("DATABASE_URL")
    if not publishable_key:
        raise RuntimeError("CLERK_PUBLISHABLE_KEY is required for authentication.")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for authentication.")

    authorized_parties = tuple(
        item.strip() for item in os.getenv("CLERK_AUTHORIZED_PARTIES", "").split(",") if item.strip()
    )
    auth_provider = ClerkAuthProvider(
        ClerkAuthConfig(
            publishable_key=publishable_key,
            secret_key=secret_key,
            frontend_api_url=os.getenv("CLERK_FRONTEND_API_URL"),
            jwks_url=os.getenv("CLERK_JWKS_URL"),
            issuer=os.getenv("CLERK_ISSUER"),
            authorized_parties=authorized_parties,
        )
    )
    users = PostgresUserRepository(database_url=database_url)
    try:
        users.ensure_schema()
    except OperationalError as exc:
        raise RuntimeError(
            "Authentication database is unavailable. Check DATABASE_URL. "
            "Railway internal hostnames such as 'postgres.railway.internal' only work inside Railway's private network."
        ) from exc
    return AuthenticateUserUseCase(auth_provider=auth_provider, users=users)


def get_current_user() -> User | None:
    session_token = get_query_param(CLERK_SESSION_TOKEN_PARAM) or get_request_cookie(CLERK_SESSION_COOKIE)
    return authenticate_session_token(session_token)


def authenticate_session_token(session_token: str | None) -> User | None:
    if not session_token:
        get_session_state().pop(AUTH_ERROR_KEY, None)
        return None

    try:
        current_user = build_authenticate_user_use_case().execute(session_token)
        get_session_state().pop(AUTH_ERROR_KEY, None)
        clear_query_param(CLERK_SESSION_TOKEN_PARAM)
        return current_user
    except RuntimeError as exc:
        get_session_state()[AUTH_ERROR_KEY] = str(exc)
        logger.warning("Authentication is not configured: %s", exc)
        return None
    except AuthenticationError as exc:
        get_session_state()[AUTH_ERROR_KEY] = f"Authentication failed: {exc}"
        clear_query_param(CLERK_SESSION_TOKEN_PARAM)
        logger.warning("Authentication failed: %s", exc)
        return None


def mount_clerk_auth_bridge(publishable_key: str, auth_error: str | None) -> str | None:
    result = get_clerk_auth_bridge()(
        data={
            "publishableKey": publishable_key,
            "host": derive_clerk_frontend_api_host(publishable_key),
            "authError": auth_error or "",
        },
        key="clerk_auth_bridge",
    )
    return getattr(result, "session_token", None)


def render_auth_gate() -> str | None:
    render_brivoly_auth_panel()
    st.caption("Secure sign-in for Brivoly. Authentication is powered by Clerk while the app keeps its own internal user record.")

    publishable_key = os.getenv("CLERK_PUBLISHABLE_KEY")
    database_url = os.getenv("DATABASE_URL")
    if not publishable_key:
        st.error("Authentication is not configured. Set CLERK_PUBLISHABLE_KEY.")
        return None

    if not database_url:
        st.error("Authentication database is not configured. Set DATABASE_URL before completing sign-in.")

    sign_up_url = get_configured_clerk_page_url("sign-up")
    if sign_up_url:
        st.caption("New to Brivoly?")
        st.markdown(f"[Create an account]({sign_up_url})")
    else:
        st.caption(
            "Need self-service signup? Set CLERK_SIGN_UP_URL from Clerk Dashboard > Account Portal > Pages."
        )

    auth_error = get_session_state().get(AUTH_ERROR_KEY)
    if auth_error:
        st.error(auth_error)
        st.caption("Clerk may already have an active session. Fix the app database connection, then refresh this page.")

    return mount_clerk_auth_bridge(publishable_key, str(auth_error) if auth_error else None)


def render_account_widget() -> None:
    publishable_key = os.getenv("CLERK_PUBLISHABLE_KEY")
    if not publishable_key:
        return

    get_clerk_account_widget()(
        data={
            "publishableKey": publishable_key,
            "host": derive_clerk_frontend_api_host(publishable_key),
        },
        key="clerk_account_widget",
    )


def derive_clerk_frontend_api_host(publishable_key: str) -> str:
    config = ClerkAuthConfig(publishable_key=publishable_key)
    return config.resolved_frontend_api_url.removeprefix("https://")


def get_app_base_url() -> str:
    return os.getenv("APP_BASE_URL") or os.getenv("PUBLIC_APP_URL") or "http://localhost:8501"


def get_configured_clerk_page_url(page: str) -> str | None:
    env_name = "CLERK_SIGN_IN_URL" if page == "sign-in" else "CLERK_SIGN_UP_URL"
    value = os.getenv(env_name, "").strip()
    if not value:
        return None
    if value.startswith("http://") or value.startswith("https://"):
        return with_redirect_url(value, get_app_base_url())
    return with_redirect_url(f"{get_app_base_url().rstrip('/')}/{value.lstrip('/')}", get_app_base_url())


def with_redirect_url(url: str, redirect_url: str) -> str:
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("redirect_url", redirect_url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def build_price_chart(close: pd.DataFrame, benchmark: str) -> go.Figure:
    bench = close[benchmark].dropna()
    ma50 = bench.rolling(50).mean()
    ma200 = bench.rolling(200).mean()

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=bench.index, y=bench, name=f"{benchmark} Price", line={"width": 2}))
    fig.add_trace(go.Scatter(x=ma50.index, y=ma50, name="50D MA", line={"dash": "dot"}))
    fig.add_trace(go.Scatter(x=ma200.index, y=ma200, name="200D MA", line={"dash": "dash"}))
    fig.update_layout(height=420, margin={"l": 12, "r": 12, "t": 24, "b": 12}, legend={"orientation": "h"})
    return fig


def build_buyer_participation_chart(close: pd.DataFrame) -> go.Figure:
    buyer_participation = compute_buyer_participation_series(close).rolling(20).mean()
    new_high_ratio = compute_new_high_ratio_series(close)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=buyer_participation.index,
            y=buyer_participation,
            name="Buyer Participation (20D)",
            line={"width": 2, "color": "#d97706"},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=new_high_ratio.index,
            y=new_high_ratio,
            name="New High Ratio (252D)",
            line={"width": 2, "dash": "dash", "color": "#2563eb"},
        )
    )
    fig.update_layout(
        height=320,
        margin={"l": 12, "r": 12, "t": 24, "b": 12},
        legend={"orientation": "h"},
        yaxis={"range": [0, 1], "tickformat": ".0%"},
    )
    return fig


@st.cache_data(ttl=900)
def run_dashboard(
    universe: tuple[str, ...],
    benchmark: str,
    vix_symbol: str,
    risk_proxy: str,
    short_yield_symbol: str,
    long_yield_symbol: str,
    start_date: date,
    end_date: date,
) -> tuple[object, datetime]:
    config = DashboardConfig(
        universe=list(universe),
        benchmark=benchmark,
        vix_symbol=vix_symbol,
        risk_proxy=risk_proxy,
        short_yield_symbol=short_yield_symbol,
        long_yield_symbol=long_yield_symbol,
        start_date=start_date,
        end_date=end_date,
    )
    use_case = BuildCrashDashboardUseCase(market_data=YFinanceMarketDataAdapter())
    logger.info(
        "Refreshing dashboard data for %s through %s",
        start_date.isoformat(),
        end_date.isoformat(),
    )
    return use_case.execute(config), datetime.now().astimezone()


def schedule_refresh(interval_seconds: int = REFRESH_INTERVAL_SECONDS) -> None:
    st_autorefresh(interval=interval_seconds * 1000, key="market_crash_monitor_refresh")


def format_refresh_timestamp(refreshed_at: datetime) -> str:
    return refreshed_at.astimezone(DISPLAY_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S %Z")


def clear_dashboard_cache() -> None:
    clear = getattr(run_dashboard, "clear", None)
    if clear is not None:
        logger.info("Clearing cached dashboard data")
        clear()


def get_secret(name: str) -> str | None:
    value = os.getenv(name)
    if value:
        return value

    try:
        secrets = getattr(st, "secrets", None)
        if secrets is None:
            return None

        secret_value = secrets.get(name)
    except StreamlitSecretNotFoundError:
        return None

    return str(secret_value) if secret_value else None


def get_telegram_status() -> str:
    bot_token = get_secret("TELEGRAM_BOT_TOKEN")
    chat_id = get_secret("TELEGRAM_CHAT_ID")
    if not bot_token and not chat_id:
        return "Telegram: missing Railway env vars"
    if not bot_token:
        return "Telegram: bot token missing"
    if not chat_id:
        return "Telegram: chat ID missing"

    status = st.session_state.get(TELEGRAM_STATUS_KEY)
    return f"Telegram: {status}" if status else "Telegram: configured"


def get_telegram_status_style() -> tuple[str, str]:
    bot_token = get_secret("TELEGRAM_BOT_TOKEN")
    chat_id = get_secret("TELEGRAM_CHAT_ID")
    if not bot_token and not chat_id:
        return "gray", "missing Railway env vars"
    if not bot_token or not chat_id:
        return "orange", get_telegram_status().replace("Telegram: ", "")

    status = st.session_state.get(TELEGRAM_STATUS_KEY)
    if status == "alert sent":
        return "green", "alert sent"
    if status == "startup message sent":
        return "green", "startup message sent"
    return "blue", "configured"


def should_send_telegram_alert(result: object) -> bool:
    actions = getattr(result, "actions", [])
    score = getattr(result, "risk_score", 0.0)
    return score >= CAUTION_CUTOFF or any(
        keyword in action
        for action in actions
        for keyword in ("Buy-the-dip signal", "Watchlist dip", "Yield curve inverted")
    )


def build_alert_signature(result: object, benchmark: str) -> str:
    actions = tuple(getattr(result, "actions", []))
    regime = getattr(result, "regime", "")
    score = round(float(getattr(result, "risk_score", 0.0)), 1)
    return repr((benchmark, regime, score, actions))


def build_telegram_alert_message(result: object, benchmark: str, refreshed_at: datetime) -> str:
    actions = "\n".join(f"- {action}" for action in getattr(result, "actions", []))
    return (
        f"Market Crash Monitor alert for {benchmark}\n"
        f"Regime: {getattr(result, 'regime', 'Unknown')}\n"
        f"Risk score: {float(getattr(result, 'risk_score', 0.0)):.1f}/100\n"
        f"Refreshed: {format_refresh_timestamp(refreshed_at)}\n"
        f"Actions:\n{actions}"
    )


def build_startup_message(benchmark: str, refreshed_at: datetime) -> str:
    return (
        f"Market Crash Monitor started for {benchmark}\n"
        f"Startup time: {format_refresh_timestamp(refreshed_at)}"
    )


def maybe_send_startup_telegram_message(benchmark: str, refreshed_at: datetime) -> None:
    if st.session_state.get(STARTUP_MESSAGE_SENT_KEY):
        return

    bot_token = get_secret("TELEGRAM_BOT_TOKEN")
    chat_id = get_secret("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        return

    notifier = TelegramNotifier(bot_token=bot_token, chat_id=chat_id)
    logger.info("Sending Telegram startup message for %s", benchmark)
    notifier.send_message(build_startup_message(benchmark, refreshed_at))
    st.session_state[STARTUP_MESSAGE_SENT_KEY] = "sent"
    st.session_state[TELEGRAM_STATUS_KEY] = "startup message sent"


def build_action_condition_rows(result: object) -> pd.DataFrame:
    score = float(getattr(result, "risk_score", 0.0))
    metrics = getattr(result, "metrics", {})
    rows: list[dict[str, str]] = []

    if score >= RISK_OFF_CUTOFF:
        rows.append(
            {
                "Suggestion": "De-risk aggressively",
                "Conditions": "Crash risk score >= 70, showing elevated trend, drawdown, volatility, or breadth stress.",
            }
        )
    elif score >= CAUTION_CUTOFF:
        rows.append(
            {
                "Suggestion": "Partial de-risk",
                "Conditions": "Crash risk score between 50 and 70, so the market is fragile but not fully risk-off.",
            }
        )
    else:
        rows.append(
            {
                "Suggestion": "Maintain strategic risk",
                "Conditions": "Crash risk score below 50, so broad stress is still contained.",
            }
        )

    dip_zone = -0.20 < float(metrics.get("drawdown_252", 0.0)) < -0.05
    oversold = float(metrics.get("rsi14", 100.0)) < 35
    trend_reclaim = float(metrics.get("price", 0.0)) > float(metrics.get("ma50", float("inf")))
    vix_cooling = "vix" in metrics and "vix_sma20" in metrics and float(metrics["vix"]) < float(metrics["vix_sma20"])

    if dip_zone and oversold and (trend_reclaim or vix_cooling):
        rows.append(
            {
                "Suggestion": "Buy-the-dip staging",
                "Conditions": "Drawdown is between -20% and -5%, RSI is below 35, and either trend is reclaiming or VIX is cooling.",
            }
        )
    elif dip_zone and oversold:
        rows.append(
            {
                "Suggestion": "Watchlist dip",
                "Conditions": "Drawdown is between -20% and -5% and RSI is below 35, but trend reclaim or VIX cooling is still missing.",
            }
        )

    if float(metrics.get("yield_curve_spread", 0.0)) < 0:
        rows.append(
            {
                "Suggestion": "Yield curve caution",
                "Conditions": "Yield curve spread is negative, so the term structure is inverted.",
            }
        )

    buyer_exhaustion = float(metrics.get("buyer_exhaustion", 0.0))
    buyer_participation = float(metrics.get("buyer_participation_20d", 1.0))
    new_high_ratio = float(metrics.get("new_high_ratio_252", 1.0))
    if buyer_exhaustion >= 70 or (buyer_participation < 0.45 and new_high_ratio < 0.25):
        rows.append(
            {
                "Suggestion": "No more buyers",
                "Conditions": "Buyer participation is weak and few names are near 252-day highs, so rallies may be running out of sponsorship.",
            }
        )

    return pd.DataFrame(rows)


def maybe_send_telegram_alert(result: object, benchmark: str, refreshed_at: datetime) -> None:
    if not should_send_telegram_alert(result):
        return

    bot_token = get_secret("TELEGRAM_BOT_TOKEN")
    chat_id = get_secret("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        return

    signature = build_alert_signature(result, benchmark)
    if st.session_state.get(LAST_ALERT_SIGNATURE_KEY) == signature:
        return

    notifier = TelegramNotifier(bot_token=bot_token, chat_id=chat_id)
    logger.info("Sending Telegram alert for %s with signature %s", benchmark, signature)
    notifier.send_message(build_telegram_alert_message(result, benchmark, refreshed_at))
    st.session_state[LAST_ALERT_SIGNATURE_KEY] = signature
    st.session_state[TELEGRAM_STATUS_KEY] = "alert sent"


def render() -> None:
    st.set_page_config(page_title="Crash Monitor Dashboard", layout="wide")
    schedule_refresh()
    logger.info("Rendering dashboard UI")
    st.title("Market Crash Monitor")
    st.caption(
        "Tracks stress indicators and provides systematic de-risk / dip-buy cues. "
        "Educational use only, not investment advice."
    )

    current_user = get_current_user()
    if current_user is None:
        current_user = authenticate_session_token(render_auth_gate())
        if current_user is None:
            return

    benchmark = "SPY"
    vix_symbol = "^VIX"
    risk_proxy = "HYG"
    short_yield_symbol = "^IRX"
    long_yield_symbol = "^TNX"
    lookback_years = 4
    force_refresh = False
    universe = list(DEFAULT_UNIVERSE)

    with st.sidebar:
        st.header("Account")
        st.markdown(f"Signed in as: `{current_user.display_name or current_user.email or current_user.auth_subject}`")
        if current_user.email:
            st.caption(current_user.email)
        render_account_widget()

        st.header("Settings")
        universe_text = st.text_input("Risk Universe (comma-separated)", ", ".join(DEFAULT_UNIVERSE))
        benchmark = st.text_input("Benchmark Symbol", benchmark).upper().strip()
        vix_symbol = st.text_input("Fear Gauge Symbol", vix_symbol).upper().strip()
        risk_proxy = st.text_input("Risk Proxy Symbol (credit/risk appetite)", risk_proxy).upper().strip()
        short_yield_symbol = st.text_input("Short Yield Symbol", short_yield_symbol).upper().strip()
        long_yield_symbol = st.text_input("Long Yield Symbol", long_yield_symbol).upper().strip()
        lookback_years = st.slider("Lookback (years)", min_value=1, max_value=10, value=lookback_years)
        force_refresh = st.button("Refresh Now")
        universe = [t.strip().upper() for t in universe_text.split(",") if t.strip()]

        status_color, status_text = get_telegram_status_style()
        st.markdown(f":{status_color}[Telegram: {status_text}]")

    end_date = date.today()
    start_date = end_date - timedelta(days=365 * lookback_years)

    if force_refresh:
        clear_dashboard_cache()

    try:
        result, refreshed_at = run_dashboard(
            tuple(universe),
            benchmark,
            vix_symbol,
            risk_proxy,
            short_yield_symbol,
            long_yield_symbol,
            start_date,
            end_date,
        )
    except ValueError as exc:
        st.error(str(exc))
        return

    try:
        maybe_send_telegram_alert(result, benchmark, refreshed_at)
    except TelegramNotificationError as exc:
        st.warning(str(exc))

    st.caption(f"Last refreshed: {format_refresh_timestamp(refreshed_at)}")

    metrics = result.metrics
    risk_color = "red" if result.risk_score >= RISK_OFF_CUTOFF else "orange" if result.risk_score >= CAUTION_CUTOFF else "green"

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Crash Risk Score", f"{result.risk_score:.1f}/100")
    c2.metric("252D Drawdown", f"{metrics['drawdown_252']:.1%}")
    c3.metric("20D Vol (Ann.)", f"{metrics['vol20']:.1%}")
    c4.metric("Breadth >200D", f"{metrics['breadth_ratio']:.1%}")
    if "yield_curve_spread" in metrics:
        c5.metric("Yield Spread (L-S)", f"{metrics['yield_curve_spread']:.2f}%")
    else:
        c5.metric("Yield Spread (L-S)", "N/A")

    st.markdown(f"**Regime:** :{risk_color}[{result.regime}]")
    if "yield_curve_spread" in metrics:
        curve_text = "Inverted" if metrics["yield_curve_spread"] < 0 else "Normal"
        curve_color = "red" if metrics["yield_curve_spread"] < 0 else "green"
        st.markdown(f"**Yield Curve:** :{curve_color}[{curve_text}]")

    st.subheader("Action Suggestions")
    for action in result.actions:
        st.write(f"- {action}")

    condition_table = build_action_condition_rows(result)
    if not condition_table.empty:
        st.subheader("Why These Suggestions Appear")
        st.dataframe(condition_table, hide_index=True, width="stretch")

    left, right = st.columns([2, 1])
    with left:
        st.subheader(f"{benchmark} Trend & Price")
        st.plotly_chart(build_price_chart(result.close_data, benchmark), width="stretch")
    with right:
        st.subheader("Risk Component Scores")
        component_df = (
            pd.DataFrame({"Component": list(result.risk_components.keys()), "Score": list(result.risk_components.values())})
            .sort_values("Score", ascending=False)
            .reset_index(drop=True)
        )
        st.dataframe(component_df, hide_index=True, width="stretch")

    st.subheader("Buyer Participation")
    st.plotly_chart(build_buyer_participation_chart(result.close_data), width="stretch")

    st.subheader("Indicators with Percentiles")
    indicator_table = result.indicator_percentiles.copy()
    if not indicator_table.empty:
        indicator_table = indicator_table.round(4)
    st.dataframe(
        indicator_table,
        hide_index=True,
        width="stretch",
    )
