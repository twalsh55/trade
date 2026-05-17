"use client";

import { useEffect, useState } from "react";

type SignOutBridgeProps = {
  publishableKey: string | null;
  host: string | null;
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
      signOut(): Promise<void>;
    };
    __internal_ClerkUICtor?: unknown;
    __brivolyClerkLoadPromise?: Promise<unknown>;
  }
}

export function SignOutBridge({ publishableKey, host }: SignOutBridgeProps) {
  const [status, setStatus] = useState("Signing you out...");

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
      if (!publishableKey || !host) {
        return null;
      }
      if (!window.__brivolyClerkLoadPromise) {
        window.__brivolyClerkLoadPromise = (async () => {
          await loadScript(`https://${host}/npm/@clerk/clerk-js@6/dist/clerk.browser.js`, {
            crossorigin: "anonymous",
            "data-clerk-publishable-key": publishableKey,
          });
          await window.Clerk?.load({
            ui: { ClerkUI: window.__internal_ClerkUICtor },
          });
        })();
      }
      await window.__brivolyClerkLoadPromise;
      return window.Clerk ?? null;
    }

    async function run() {
      try {
        const clerk = await ensureClerk();
        if (!cancelled && clerk?.signOut) {
          await clerk.signOut();
        }
      } catch {
        // Keep going so the local app session is still cleared even if Clerk JS is unavailable.
      }

      try {
        await fetch("/api/session", { method: "DELETE" });
      } finally {
        if (!cancelled) {
          window.location.replace("/sign-in?redirectTo=%2Fcrm");
        }
      }
    }

    run();

    return () => {
      cancelled = true;
    };
  }, [host, publishableKey]);

  return (
    <section className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Sign Out</p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">Closing your CRM session.</h1>
      <p className="mt-3 text-sm leading-6 text-slate-600">{status}</p>
    </section>
  );
}
