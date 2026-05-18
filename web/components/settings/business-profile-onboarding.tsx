"use client";

import type { ChangeEvent, ReactNode } from "react";
import { useEffect, useMemo, useState, useTransition } from "react";

import { Button } from "@/components/ui/button";
import { shouldPromptForBusinessProfile } from "@/lib/business-profile";
import { readImageFileAsDataUrl } from "@/lib/file-data-url";
import type { AccountSettings } from "@/lib/types";

type BusinessProfileOnboardingProps = {
  initialSettings: AccountSettings | null;
  title?: string;
  description?: string;
  accent?: "amber" | "cyan";
  onSettingsUpdated?: (settings: AccountSettings) => void;
};

export function BusinessProfileOnboarding({
  initialSettings,
  title = "Before we automate outreach, tell Brivoly the obvious basics.",
  description = "Set the business name, logo, and sender name Brivoly should use in automatic emails and account-facing relationship moments. Or skip it for now and add it later in settings.",
  accent = "amber",
  onSettingsUpdated,
}: BusinessProfileOnboardingProps) {
  const [settings, setSettings] = useState(initialSettings);
  const [businessName, setBusinessName] = useState(
    initialSettings?.business_name ?? "",
  );
  const [businessWebsite, setBusinessWebsite] = useState(
    initialSettings?.business_website ?? "",
  );
  const [senderName, setSenderName] = useState(
    initialSettings?.outbound_sender_name ?? "",
  );
  const [logoDataUrl, setLogoDataUrl] = useState(
    initialSettings?.business_logo_data_url ?? "",
  );
  const [status, setStatus] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    setSettings(initialSettings);
    setBusinessName(initialSettings?.business_name ?? "");
    setBusinessWebsite(initialSettings?.business_website ?? "");
    setSenderName(initialSettings?.outbound_sender_name ?? "");
    setLogoDataUrl(initialSettings?.business_logo_data_url ?? "");
  }, [initialSettings]);

  useEffect(() => {
    function handleSavedSettings(event: Event) {
      const customEvent = event as CustomEvent<AccountSettings>;
      if (!customEvent.detail) {
        return;
      }
      setSettings(customEvent.detail);
      setBusinessName(customEvent.detail.business_name);
      setBusinessWebsite(customEvent.detail.business_website);
      setSenderName(customEvent.detail.outbound_sender_name);
      setLogoDataUrl(customEvent.detail.business_logo_data_url);
    }

    window.addEventListener(
      "brivoly:settings-saved",
      handleSavedSettings as EventListener,
    );
    window.addEventListener(
      "trade:settings-saved",
      handleSavedSettings as EventListener,
    );
    return () => {
      window.removeEventListener(
        "brivoly:settings-saved",
        handleSavedSettings as EventListener,
      );
      window.removeEventListener(
        "trade:settings-saved",
        handleSavedSettings as EventListener,
      );
    };
  }, []);

  const visible = useMemo(
    () => shouldPromptForBusinessProfile(settings),
    [settings],
  );

  if (!settings || !visible) {
    return null;
  }

  const toneClass =
    accent === "cyan"
      ? "border-cyan-200 bg-cyan-50/90 text-cyan-950"
      : "border-amber-200 bg-amber-50/90 text-amber-950";

  function dispatchSavedSettings(saved: AccountSettings) {
    setSettings(saved);
    onSettingsUpdated?.(saved);
    window.dispatchEvent(
      new CustomEvent("brivoly:settings-saved", { detail: saved }),
    );
    window.dispatchEvent(
      new CustomEvent("trade:settings-saved", { detail: saved }),
    );
  }

  function buildPayload(overrides?: Partial<AccountSettings>): AccountSettings {
    if (!settings) {
      throw new Error("Business profile settings are unavailable.");
    }
    return {
      ...settings,
      business_name: businessName.trim(),
      business_website: businessWebsite.trim(),
      outbound_sender_name: senderName.trim(),
      business_logo_data_url: logoDataUrl.trim(),
      onboarding_profile_deferred:
        overrides?.onboarding_profile_deferred ?? false,
    };
  }

  function saveProfile(overrides?: Partial<AccountSettings>) {
    setStatus(
      overrides?.onboarding_profile_deferred
        ? "Okay, we will remind you less aggressively."
        : "Saving business profile...",
    );
    startTransition(async () => {
      try {
        const response = await fetch("/api/account/settings", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(buildPayload(overrides)),
        });
        const body = (await response.json().catch(() => null)) as
          | AccountSettings
          | { error?: string }
          | null;
        if (!response.ok || !body || !("benchmark" in body)) {
          throw new Error(
            (body && "error" in body && body.error) ||
              "Unable to save the business profile.",
          );
        }
        dispatchSavedSettings(body);
        setStatus(
          body.onboarding_profile_deferred
            ? "You can fill in the rest later from settings."
            : "Business profile saved. Brivoly can use this for branded relationship moments and automatic emails.",
        );
      } catch (error) {
        setStatus(
          error instanceof Error
            ? error.message
            : "Unable to save the business profile.",
        );
      }
    });
  }

  async function handleLogoChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    try {
      const nextLogo = await readImageFileAsDataUrl(file);
      setLogoDataUrl(nextLogo);
      setStatus(`Loaded logo preview from ${file.name}.`);
    } catch (error) {
      setStatus(
        error instanceof Error
          ? error.message
          : "Unable to load the business logo.",
      );
    } finally {
      event.target.value = "";
    }
  }

  return (
    <section className={`rounded-[1.75rem] border p-6 shadow-sm ${toneClass}`}>
      <div className="flex flex-col gap-6 xl:flex-row xl:items-start xl:justify-between">
        <div className="max-w-2xl">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] opacity-75">
            First Login Setup
          </p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight">
            {title}
          </h2>
          <p className="mt-3 text-sm leading-6 opacity-90">{description}</p>
        </div>
        <div className="rounded-[1.4rem] border border-white/70 bg-white/70 px-4 py-4 text-sm text-slate-700 xl:max-w-sm">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
            Why this matters
          </p>
          <p className="mt-2 leading-6">
            Business identity, sender naming, and a recognizable logo make
            automatic emails, imports, and follow-up touches feel intentional
            instead of generic.
          </p>
        </div>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Field label="Business name">
          <input
            className={inputClassName()}
            value={businessName}
            onChange={(event) => setBusinessName(event.target.value)}
            placeholder="Northstar Studio"
          />
        </Field>
        <Field label="Name on auto emails">
          <input
            className={inputClassName()}
            value={senderName}
            onChange={(event) => setSenderName(event.target.value)}
            placeholder="Ada from Northstar Studio"
          />
        </Field>
        <Field label="Business website">
          <input
            className={inputClassName()}
            value={businessWebsite}
            onChange={(event) => setBusinessWebsite(event.target.value)}
            placeholder="https://northstar.example"
          />
        </Field>
        <Field label="Logo">
          <div className="rounded-[1.25rem] border border-dashed border-slate-300 bg-white px-4 py-4">
            <input
              type="file"
              accept=".png,image/png,.jpg,image/jpeg,.jpeg,image/jpeg,.webp,image/webp,.svg,image/svg+xml"
              className="block w-full text-sm text-slate-700"
              onChange={handleLogoChange}
            />
            <p className="mt-2 text-xs text-slate-500">
              Use a small square or horizontal logo. Max 500 KB.
            </p>
            {logoDataUrl ? (
              <div className="mt-3 flex items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={logoDataUrl}
                  alt="Business logo preview"
                  className="h-12 w-12 rounded-xl object-cover"
                />
                <button
                  type="button"
                  className="text-sm font-medium text-slate-700 underline underline-offset-4"
                  onClick={() => setLogoDataUrl("")}
                >
                  Remove logo
                </button>
              </div>
            ) : null}
          </div>
        </Field>
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <Button
          type="button"
          disabled={isPending || !businessName.trim() || !senderName.trim()}
          onClick={() => saveProfile({ onboarding_profile_deferred: false })}
        >
          {isPending ? "Saving..." : "Save and continue"}
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={isPending}
          onClick={() => saveProfile({ onboarding_profile_deferred: true })}
        >
          Add later
        </Button>
        {status ? <p className="text-sm text-slate-600">{status}</p> : null}
      </div>
    </section>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-2">
      <span className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
        {label}
      </span>
      {children}
    </label>
  );
}

function inputClassName() {
  return "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-primary";
}
