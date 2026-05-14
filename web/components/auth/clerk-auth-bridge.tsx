"use client";

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
  const [status, setStatus] = useState("Loading sign-in...");

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
        setStatus("Loading sign-in...");
        const clerk = await ensureClerk();
        if (cancelled) {
          return;
        }

        if (clerk?.isSignedIn && clerk.session) {
          setStatus("Finalizing session...");
          const token = await clerk.session.getToken({ skipCache: true });
          if (!token) {
            setStatus("Clerk session found, but no session token was returned.");
            return;
          }
          await bootstrapSession(token);
          return;
        }

        const mountTarget = document.getElementById("clerk-auth-root");
        if (!mountTarget || !clerk) {
          setStatus("Unable to initialize the sign-in surface.");
          return;
        }
        mountTarget.replaceChildren();
        clerk.mountSignIn(mountTarget);
        setStatus("Use Clerk sign-in to continue.");
      } catch (error) {
        setStatus(error instanceof Error ? error.message : "Unable to load Clerk sign-in.");
      }
    }

    init();

    return () => {
      cancelled = true;
    };
  }, [host, publishableKey, redirectTo, router]);

  return (
    <div className="rounded-[1.75rem] border bg-white/85 p-6 shadow-sm">
      <div className="inline-flex items-center rounded-full border bg-slate-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
        Clerk session bootstrap
      </div>
      <h2 className="mt-4 text-3xl font-semibold tracking-tight text-slate-950">Sign in to Brivoly</h2>
      <p className="mt-3 max-w-xl text-sm leading-6 text-slate-600">
        Authentication happens through Clerk, then the session token is exchanged for an application cookie so the
        Next.js UI can talk to the Python API on every request.
      </p>
      <div id="clerk-auth-root" className="mt-6 min-h-[360px] rounded-[1.5rem] border bg-slate-50 p-4" />
      <p className="mt-4 text-sm text-slate-500">{status}</p>
    </div>
  );
}
