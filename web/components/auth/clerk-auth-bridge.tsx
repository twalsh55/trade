"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

type ClerkAuthBridgeProps = {
  publishableKey: string;
  host: string;
  redirectTo: string;
};

declare global {
  interface Window {
    Clerk?: {
      isSignedIn?: boolean;
      session?: {
        getToken(options?: { skipCache?: boolean }): Promise<string | null>;
      };
      load(options?: object): Promise<void>;
      mountSignIn(target: Element): void;
    };
    __internal_ClerkUICtor?: unknown;
    __brivolyClerkLoadPromise?: Promise<unknown>;
  }
}

export function ClerkAuthBridge({ publishableKey, host, redirectTo }: ClerkAuthBridgeProps) {
  const router = useRouter();
  const [status, setStatus] = useState("Loading secure sign-in...");

  useEffect(() => {
    let cancelled = false;

    async function loadScript(src: string, attributes: Record<string, string> = {}) {
      const existing = document.querySelector<HTMLScriptElement>(`script[data-brivoly-src="${src}"]`);
      if (existing) {
        if (existing.dataset.loaded === "true") {
          return;
        }
        await new Promise<void>((resolve, reject) => {
          existing.addEventListener("load", () => resolve(), { once: true });
          existing.addEventListener("error", () => reject(new Error(`Failed to load ${src}`)), { once: true });
        });
        return;
      }

      await new Promise<void>((resolve, reject) => {
        const script = document.createElement("script");
        script.src = src;
        script.async = true;
        script.dataset.brivolySrc = src;
        Object.entries(attributes).forEach(([key, value]) => script.setAttribute(key, value));
        script.addEventListener(
          "load",
          () => {
            script.dataset.loaded = "true";
            resolve();
          },
          { once: true },
        );
        script.addEventListener("error", () => reject(new Error(`Failed to load ${src}`)), { once: true });
        document.head.appendChild(script);
      });
    }

    async function ensureClerk() {
      if (!window.__brivolyClerkLoadPromise) {
        window.__brivolyClerkLoadPromise = (async () => {
          await loadScript(`https://${host}/npm/@clerk/clerk-js@6/dist/clerk.browser.js`, {
            crossorigin: "anonymous",
            "data-clerk-publishable-key": publishableKey,
          });
          await loadScript(`https://${host}/npm/@clerk/ui@1/dist/ui.browser.js`, {
            crossorigin: "anonymous",
          });
          await window.Clerk?.load({
            ui: { ClerkUI: window.__internal_ClerkUICtor },
          });
        })();
      }
      await window.__brivolyClerkLoadPromise;
      return window.Clerk;
    }

    async function bootstrapSession(sessionToken: string) {
      const response = await fetch("/api/session", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ sessionToken }),
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { error?: string } | null;
        throw new Error(payload?.error ?? "Unable to persist the authenticated session.");
      }

      router.replace(redirectTo);
      router.refresh();
    }

    async function init() {
      try {
        setStatus("Loading secure sign-in...");
        const clerk = await ensureClerk();
        if (cancelled) {
          return;
        }

        if (clerk?.isSignedIn && clerk.session) {
          setStatus("You're signed in. Finalizing your workspace...");
          const token = await clerk.session.getToken({ skipCache: true });
          if (!token) {
            setStatus("Sign-in was detected, but the secure session could not be completed. Please try again.");
            return;
          }
          await bootstrapSession(token);
          return;
        }

        const mountTarget = document.getElementById("clerk-auth-root");
        if (!mountTarget || !clerk) {
          setStatus("We could not open the sign-in form. Refresh and try again.");
          return;
        }
        mountTarget.replaceChildren();
        clerk.mountSignIn(mountTarget);
        setStatus("Sign in below to open your Brivoly workspace.");
      } catch (error) {
        setStatus(error instanceof Error ? error.message : "Unable to load sign-in.");
      }
    }

    init();

    return () => {
      cancelled = true;
    };
  }, [host, publishableKey, redirectTo, router]);

  const statusAppearance = getStatusAppearance(status);

  return (
    <div className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
      <div className="inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-emerald-700">
        Welcome back
      </div>
      <h2 className="mt-4 text-3xl font-semibold tracking-tight text-slate-950">Sign in to continue to Brivoly</h2>
      <p className="mt-3 max-w-xl text-sm leading-6 text-slate-600">
        Use your account to open the CRM workspace or crash monitor. Once you sign in, Brivoly will take you straight
        back to where you were headed.
      </p>
      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        <AuthStep label="Step 1" value="Sign in" />
        <AuthStep label="Step 2" value="Secure your session" />
        <AuthStep label="Step 3" value="Open your workspace" />
      </div>
      <div id="clerk-auth-root" className="mt-6 min-h-[360px] rounded-[1.5rem] border bg-slate-50 p-4" />
      <div className={`mt-4 rounded-[1.25rem] border px-4 py-3 text-sm ${statusAppearance.className}`}>
        <p className="font-medium">{statusAppearance.label}</p>
        <p className="mt-1">{status}</p>
      </div>
      <p className="mt-4 text-sm text-slate-500">
        New here?{" "}
        <Link className="font-medium text-slate-900 underline underline-offset-4" href="/?from=sign-in">
          Start from the workspace hub
        </Link>
        .
      </p>
    </div>
  );
}

function AuthStep({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.25rem] border bg-slate-50 px-4 py-3">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">{label}</p>
      <p className="mt-2 text-sm font-medium text-slate-900">{value}</p>
    </div>
  );
}

function getStatusAppearance(status: string) {
  const normalized = status.toLowerCase();

  if (normalized.includes("signed in") || normalized.includes("finalizing")) {
    return {
      label: "Almost there",
      className: "border-emerald-200 bg-emerald-50 text-emerald-800",
    };
  }

  if (normalized.includes("could not") || normalized.includes("unable")) {
    return {
      label: "Sign-in needs attention",
      className: "border-rose-200 bg-rose-50 text-rose-800",
    };
  }

  return {
    label: "Current status",
    className: "border-slate-200 bg-slate-50 text-slate-700",
  };
}
