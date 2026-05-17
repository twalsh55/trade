"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

type ClerkAuthBridgeProps = {
  publishableKey: string;
  host: string;
  redirectTo: string;
  mode?: "sign-in" | "sign-up";
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
      mountSignUp(target: Element): void;
    };
    __internal_ClerkUICtor?: unknown;
    __brivolyClerkLoadPromise?: Promise<unknown>;
  }
}

export function ClerkAuthBridge({ publishableKey, host, redirectTo, mode = "sign-in" }: ClerkAuthBridgeProps) {
  const router = useRouter();
  const isSignUp = mode === "sign-up";
  const [status, setStatus] = useState(isSignUp ? "Loading secure account creation..." : "Loading secure sign-in...");
  const [isCompleting, setIsCompleting] = useState(false);

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
      setIsCompleting(true);
      const response = await fetch("/api/session", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ sessionToken }),
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { error?: string } | null;
        setIsCompleting(false);
        throw new Error(payload?.error ?? "Unable to persist the authenticated session.");
      }

      router.replace(redirectTo);
    }

    async function init() {
      try {
        setStatus(isSignUp ? "Loading secure account creation..." : "Loading secure sign-in...");
        const clerk = await ensureClerk();
        if (cancelled) {
          return;
        }

        if (clerk?.isSignedIn && clerk.session) {
          setStatus(isSignUp ? "Your account is ready. Finalizing your workspace..." : "You're signed in. Finalizing your workspace...");
          const token = await clerk.session.getToken({ skipCache: true });
          if (!token) {
            setStatus(
              isSignUp
                ? "Account creation was detected, but the secure session could not be completed. Please try again."
                : "Sign-in was detected, but the secure session could not be completed. Please try again.",
            );
            return;
          }
          await bootstrapSession(token);
          return;
        }

        const mountTarget = document.getElementById("clerk-auth-root");
        if (!mountTarget || !clerk) {
          setStatus(isSignUp ? "We could not open account creation. Refresh and try again." : "We could not open the sign-in form. Refresh and try again.");
          return;
        }
        mountTarget.replaceChildren();
        if (isSignUp) {
          clerk.mountSignUp(mountTarget);
          setStatus("Create your account below to open your Brivoly workspace.");
        } else {
          clerk.mountSignIn(mountTarget);
          setStatus("Sign in below to open your Brivoly workspace.");
        }
      } catch (error) {
        setStatus(error instanceof Error ? error.message : isSignUp ? "Unable to load account creation." : "Unable to load sign-in.");
      }
    }

    init();

    return () => {
      cancelled = true;
    };
  }, [host, isSignUp, mode, publishableKey, redirectTo, router]);

  const statusAppearance = getStatusAppearance(status);

  return (
    <div className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">{isSignUp ? "Secure Sign-Up" : "Secure Sign-In"}</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">
            {isSignUp ? "Create your account and open Brivoly in one step." : "Open Brivoly and continue where you left off."}
          </h2>
        </div>
        <div className="inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-emerald-700">
          {isSignUp ? "New workspace" : "Welcome back"}
        </div>
      </div>
      <p className="mt-3 max-w-xl text-sm leading-6 text-slate-600">
        {isSignUp
          ? "Create your account here, and Brivoly will secure the session and take you straight into the CRM workspace."
          : "Use your account to open the CRM workspace. Once you sign in, Brivoly will take you straight back to where you were headed."}
      </p>
      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        <AuthStep label="Step 1" value={isSignUp ? "Create account" : "Sign in"} />
        <AuthStep label="Step 2" value="Secure your session" />
        <AuthStep label="Step 3" value="Open your workspace" />
      </div>
      <div className="mt-5 rounded-[1.4rem] border bg-slate-50/80 px-4 py-4">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">What happens next</p>
        <p className="mt-2 text-sm leading-6 text-slate-700">
          {isSignUp
            ? "Brivoly will finish account creation, secure the session, and load your CRM workspace as soon as everything is ready."
            : "Brivoly will restore your queue, reminders, and saved account context as soon as the secure session is ready."}
        </p>
      </div>
      <div className="relative mt-6 min-h-[360px] overflow-hidden rounded-[1.5rem] border bg-slate-50 p-4">
        <div
          id="clerk-auth-root"
          className={`min-h-[328px] transition duration-300 ${isCompleting ? "translate-y-2 opacity-0" : "opacity-100"}`}
        />
        {isCompleting ? (
          <div className="absolute inset-0 flex items-center justify-center bg-[linear-gradient(180deg,rgba(248,250,252,0.96),rgba(255,255,255,0.98))] px-6">
            <div className="w-full max-w-md rounded-[1.6rem] border border-white bg-white/95 p-6 shadow-[0_24px_90px_-55px_rgba(15,23,42,0.35)]">
              <div className="inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-emerald-800">
                Signed in
              </div>
              <h3 className="mt-4 text-2xl font-semibold tracking-tight text-slate-950">Opening your CRM workspace.</h3>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                We’re securing your session and loading the app so the handoff feels cleaner.
              </p>
              <div className="mt-5 flex items-center gap-3">
                <div className="h-3 w-3 animate-pulse rounded-full bg-cyan-500" />
                <div className="h-3 w-3 animate-pulse rounded-full bg-cyan-400 [animation-delay:120ms]" />
                <div className="h-3 w-3 animate-pulse rounded-full bg-cyan-300 [animation-delay:240ms]" />
              </div>
              <div className="mt-6 space-y-3">
                <div className="h-3 w-4/5 animate-pulse rounded-full bg-slate-200" />
                <div className="h-3 w-full animate-pulse rounded-full bg-slate-200" />
                <div className="h-3 w-2/3 animate-pulse rounded-full bg-slate-200" />
              </div>
            </div>
          </div>
        ) : null}
      </div>
      <div className={`mt-4 rounded-[1.25rem] border px-4 py-3 text-sm ${statusAppearance.className}`}>
        <p className="font-medium">{statusAppearance.label}</p>
        <p className="mt-1">{status}</p>
      </div>
      <div className="mt-4 rounded-[1.25rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
        <p className="font-medium">Account state</p>
        <p className="mt-1">
          Until this finishes, Brivoly treats you as signed out. Once the secure session is completed, you will be
          redirected automatically.
        </p>
      </div>
      <p className="mt-4 text-sm text-slate-500">
        New here?{" "}
        <Link className="font-medium text-slate-900 underline underline-offset-4" href="/crm">
          Start from the CRM app
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
