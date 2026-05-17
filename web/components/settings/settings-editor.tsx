"use client";

import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useEffect, useState, useTransition } from "react";

import { Button } from "@/components/ui/button";
import { readImageFileAsDataUrl } from "@/lib/file-data-url";
import type { AccountSettings } from "@/lib/types";

type SettingsEditorProps = {
  initialSettings: AccountSettings | null;
  fallbackUniverse: string[];
  fallbackLookbackYears: number;
};

export function SettingsEditor({
  initialSettings,
  fallbackUniverse,
  fallbackLookbackYears,
}: SettingsEditorProps) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [status, setStatus] = useState<string | null>(null);
  const [errors, setErrors] = useState<Partial<Record<keyof AccountSettings, string>>>({});
  const [form, setForm] = useState<AccountSettings>(
    initialSettings ?? {
      universe: fallbackUniverse,
      benchmark: "SPY",
      vix_symbol: "^VIX",
      risk_proxy: "HYG",
      short_yield_symbol: "^IRX",
      long_yield_symbol: "^TNX",
      lookback_years: fallbackLookbackYears,
      telegram_enabled: false,
      business_name: "",
      business_website: "",
      outbound_sender_name: "",
      profile_alias: "",
      business_logo_data_url: "",
      onboarding_profile_deferred: false,
      crm_ai_prompt:
        "Focus on extracting follow-up-critical CRM fields from messy spreadsheets, files, and images. Prioritize lead name, company, owner, stage, next follow-up date, notes, and next step. Preserve evidence when uncertain.",
      crm_preferred_import_formats: ["csv", "google_sheets", "spreadsheet_screenshot"],
      crm_image_intake_channels: ["upload", "magic_link"],
      crm_image_intake_notes:
        "Default to uploads inside Brivoly, then use the signed magic link when phone capture is easier.",
      preferred_language: "en",
      preferred_locale: "en-US",
      data_retention_days: 365,
      allow_ai_processing: true,
      privacy_consent_version: "v1",
      privacy_consent_granted_at: null,
    },
  );

  useEffect(() => {
    function handleSavedSettings(event: Event) {
      const customEvent = event as CustomEvent<AccountSettings>;
      if (!customEvent.detail) {
        return;
      }
      setForm(customEvent.detail);
    }

    window.addEventListener("brivoly:settings-saved", handleSavedSettings as EventListener);
    window.addEventListener("trade:settings-saved", handleSavedSettings as EventListener);
    return () => {
      window.removeEventListener("brivoly:settings-saved", handleSavedSettings as EventListener);
      window.removeEventListener("trade:settings-saved", handleSavedSettings as EventListener);
    };
  }, []);

  function updateField<K extends keyof AccountSettings>(key: K, value: AccountSettings[K]) {
    setForm((current) => ({ ...current, [key]: value }));
    setErrors((current) => ({ ...current, [key]: undefined }));
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus(null);
    const payload: AccountSettings = {
      ...form,
      universe: form.universe.map((item) => item.trim().toUpperCase()).filter(Boolean),
      benchmark: form.benchmark.trim().toUpperCase(),
      vix_symbol: form.vix_symbol.trim().toUpperCase(),
      risk_proxy: form.risk_proxy.trim().toUpperCase(),
      short_yield_symbol: form.short_yield_symbol.trim().toUpperCase(),
      long_yield_symbol: form.long_yield_symbol.trim().toUpperCase(),
      business_name: form.business_name.trim(),
      business_website: form.business_website.trim(),
      outbound_sender_name: form.outbound_sender_name.trim(),
      profile_alias: form.profile_alias.trim(),
      business_logo_data_url: form.business_logo_data_url.trim(),
      onboarding_profile_deferred:
        form.onboarding_profile_deferred &&
        !(form.business_name.trim() && form.outbound_sender_name.trim()),
      crm_ai_prompt: form.crm_ai_prompt.trim(),
      crm_preferred_import_formats: form.crm_preferred_import_formats.map((item) => item.trim()).filter(Boolean),
      crm_image_intake_channels: form.crm_image_intake_channels.map((item) => item.trim()).filter(Boolean),
      crm_image_intake_notes: form.crm_image_intake_notes.trim(),
      preferred_language: form.preferred_language.trim(),
      preferred_locale: form.preferred_locale.trim(),
      data_retention_days: Number(form.data_retention_days),
      allow_ai_processing: form.allow_ai_processing,
      privacy_consent_version: form.privacy_consent_version.trim(),
      privacy_consent_granted_at: form.privacy_consent_granted_at,
    };
    const validationErrors = validateForm(payload);
    setErrors(validationErrors);
    if (Object.keys(validationErrors).length > 0) {
      setStatus("Fix the highlighted settings fields before saving.");
      return;
    }

    setStatus("Saving settings...");

    const response = await fetch("/api/account/settings", {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    const body = (await response.json().catch(() => null)) as AccountSettings | { error?: string } | null;
    if (!response.ok) {
      setStatus((body && "error" in body && body.error) || "Unable to save settings.");
      return;
    }

    setForm(body as AccountSettings);
    setStatus("Settings saved. Refreshing dashboard snapshot...");
    window.dispatchEvent(new CustomEvent("brivoly:settings-saved", { detail: body }));
    window.dispatchEvent(new CustomEvent("trade:settings-saved", { detail: body }));
    startTransition(() => {
      router.refresh();
    });
  }

  async function handlePrivacyExport() {
    setStatus("Preparing your account data export...");
    const response = await fetch("/api/account/privacy/export");
    const body = (await response.json().catch(() => null)) as Record<string, unknown> | null;
    if (!response.ok || !body) {
      setStatus((body && typeof body.error === "string" && body.error) || "Unable to export account data.");
      return;
    }

    const blob = new Blob([JSON.stringify(body, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `brivoly-account-export-${new Date().toISOString().slice(0, 10)}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
    setStatus("Account export downloaded.");
  }

  async function handlePrivacyErase(scope: "relationship_memory" | "all_memory") {
    setStatus(scope === "all_memory" ? "Erasing saved relationship memory and mailbox links..." : "Erasing saved relationship memory...");
    const response = await fetch("/api/account/privacy/erase", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scope, confirm: true }),
    });
    const body = (await response.json().catch(() => null)) as { erased?: boolean; error?: string } | null;
    if (!response.ok || !body?.erased) {
      setStatus((body && body.error) || "Unable to erase account data.");
      return;
    }
    setStatus(scope === "all_memory" ? "Relationship memory and mailbox links were erased." : "Relationship memory was erased.");
    startTransition(() => {
      router.refresh();
    });
  }

  return (
    <form className="space-y-4" onSubmit={handleSubmit}>
      <section className="rounded-[1.5rem] border bg-slate-50/80 p-4">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Business Profile</p>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          Brivoly uses this brand context when it names automatic emails, personalizes onboarding, and presents the CRM workspace.
        </p>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <Field label="User alias">
            <input
              className={inputClassName(Boolean(errors.profile_alias))}
              value={form.profile_alias}
              onChange={(event) => updateField("profile_alias", event.target.value)}
              placeholder="tom"
            />
            {errors.profile_alias ? <FieldError message={errors.profile_alias} /> : null}
          </Field>
          <Field label="Business name">
            <input
              className={inputClassName(Boolean(errors.business_name))}
              value={form.business_name}
              onChange={(event) => updateField("business_name", event.target.value)}
            />
            {errors.business_name ? <FieldError message={errors.business_name} /> : null}
          </Field>
          <Field label="Name on auto emails">
            <input
              className={inputClassName(Boolean(errors.outbound_sender_name))}
              value={form.outbound_sender_name}
              onChange={(event) => updateField("outbound_sender_name", event.target.value)}
            />
            {errors.outbound_sender_name ? <FieldError message={errors.outbound_sender_name} /> : null}
          </Field>
          <Field label="Business website">
            <input
              className={inputClassName(Boolean(errors.business_website))}
              value={form.business_website}
              onChange={(event) => updateField("business_website", event.target.value)}
              placeholder="https://example.com"
            />
            {errors.business_website ? <FieldError message={errors.business_website} /> : null}
          </Field>
          <Field label="Logo">
            <div className="rounded-2xl border border-dashed border-slate-300 bg-white px-4 py-4">
              <input
                type="file"
                accept=".png,image/png,.jpg,image/jpeg,.jpeg,image/jpeg,.webp,image/webp,.svg,image/svg+xml"
                className="block w-full text-sm text-slate-700"
                onChange={async (event) => {
                  const file = event.target.files?.[0];
                  if (!file) {
                    return;
                  }
                  try {
                    updateField("business_logo_data_url", await readImageFileAsDataUrl(file));
                    setStatus(`Loaded logo preview from ${file.name}.`);
                  } catch (error) {
                    setStatus(error instanceof Error ? error.message : "Unable to load logo preview.");
                  } finally {
                    event.target.value = "";
                  }
                }}
              />
              <p className="mt-2 text-xs text-slate-500">Small PNG, JPG, WEBP, or SVG. Max 500 KB.</p>
              {form.business_logo_data_url ? (
                <div className="mt-3 flex items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={form.business_logo_data_url} alt="Business logo preview" className="h-12 w-12 rounded-xl object-cover" />
                  <button
                    type="button"
                    className="text-sm font-medium text-slate-700 underline underline-offset-4"
                    onClick={() => updateField("business_logo_data_url", "")}
                  >
                    Remove logo
                  </button>
                </div>
              ) : null}
            </div>
            {errors.business_logo_data_url ? <FieldError message={errors.business_logo_data_url} /> : null}
          </Field>
        </div>
      </section>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Benchmark">
          <input
            data-testid="settings-benchmark-input"
            className={inputClassName(Boolean(errors.benchmark))}
            value={form.benchmark}
            onChange={(event) => updateField("benchmark", event.target.value)}
          />
          {errors.benchmark ? <FieldError message={errors.benchmark} /> : null}
        </Field>
        <Field label="Universe">
          <input
            className={inputClassName(Boolean(errors.universe))}
            value={form.universe.join(", ")}
            onChange={(event) =>
              updateField(
                "universe",
                event.target.value.split(",").map((item) => item.trim()),
              )
            }
          />
          {errors.universe ? <FieldError message={errors.universe} /> : null}
        </Field>
        <Field label="Fear Gauge">
          <input
            className={inputClassName(Boolean(errors.vix_symbol))}
            value={form.vix_symbol}
            onChange={(event) => updateField("vix_symbol", event.target.value)}
          />
          {errors.vix_symbol ? <FieldError message={errors.vix_symbol} /> : null}
        </Field>
        <Field label="Risk Proxy">
          <input
            className={inputClassName(Boolean(errors.risk_proxy))}
            value={form.risk_proxy}
            onChange={(event) => updateField("risk_proxy", event.target.value)}
          />
          {errors.risk_proxy ? <FieldError message={errors.risk_proxy} /> : null}
        </Field>
        <Field label="Short Yield">
          <input
            className={inputClassName(Boolean(errors.short_yield_symbol))}
            value={form.short_yield_symbol}
            onChange={(event) => updateField("short_yield_symbol", event.target.value)}
          />
          {errors.short_yield_symbol ? <FieldError message={errors.short_yield_symbol} /> : null}
        </Field>
        <Field label="Long Yield">
          <input
            className={inputClassName(Boolean(errors.long_yield_symbol))}
            value={form.long_yield_symbol}
            onChange={(event) => updateField("long_yield_symbol", event.target.value)}
          />
          {errors.long_yield_symbol ? <FieldError message={errors.long_yield_symbol} /> : null}
        </Field>
        <Field label="Lookback (years)">
          <input
            type="number"
            min={1}
            max={10}
            className={inputClassName(Boolean(errors.lookback_years))}
            value={form.lookback_years}
            onChange={(event) => updateField("lookback_years", Number(event.target.value))}
          />
          {errors.lookback_years ? <FieldError message={errors.lookback_years} /> : null}
        </Field>
        <Field label="Telegram">
          <label className="flex h-[50px] items-center gap-3 rounded-2xl border bg-white px-4 py-3 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={form.telegram_enabled}
              onChange={(event) => updateField("telegram_enabled", event.target.checked)}
            />
            Enable Telegram alerts in dashboard defaults
          </label>
        </Field>
        <Field label="AI Intake Formats">
          <input
            className={inputClassName(Boolean(errors.crm_preferred_import_formats))}
            value={form.crm_preferred_import_formats.join(", ")}
            onChange={(event) =>
              updateField(
                "crm_preferred_import_formats",
                event.target.value.split(",").map((item) => item.trim()),
              )
            }
          />
          {errors.crm_preferred_import_formats ? <FieldError message={errors.crm_preferred_import_formats} /> : null}
        </Field>
        <Field label="Image Intake Channels">
          <input
            className={inputClassName(Boolean(errors.crm_image_intake_channels))}
            value={form.crm_image_intake_channels.join(", ")}
            onChange={(event) =>
              updateField(
                "crm_image_intake_channels",
                event.target.value.split(",").map((item) => item.trim()),
              )
            }
          />
          {errors.crm_image_intake_channels ? <FieldError message={errors.crm_image_intake_channels} /> : null}
        </Field>
      </div>

      <Field label="AI Intake Prompt">
        <textarea
          className={inputClassName(Boolean(errors.crm_ai_prompt))}
          value={form.crm_ai_prompt}
          onChange={(event) => updateField("crm_ai_prompt", event.target.value)}
          rows={5}
        />
        {errors.crm_ai_prompt ? <FieldError message={errors.crm_ai_prompt} /> : null}
      </Field>
      <Field label="Image Intake Routing Notes">
        <textarea
          className={inputClassName(Boolean(errors.crm_image_intake_notes))}
          value={form.crm_image_intake_notes}
          onChange={(event) => updateField("crm_image_intake_notes", event.target.value)}
          rows={4}
        />
        {errors.crm_image_intake_notes ? <FieldError message={errors.crm_image_intake_notes} /> : null}
      </Field>

      <section className="rounded-[1.5rem] border bg-slate-50/80 p-4">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Language and privacy</p>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          Set a default language and locale for Brivoly’s copy and formatting, then keep retention and AI handling clear for GDPR-oriented account controls.
        </p>
        <div className="mt-4 grid gap-4 xl:grid-cols-2">
          <Field label="Preferred language">
            <input
              className={inputClassName(Boolean(errors.preferred_language))}
              value={form.preferred_language}
              onChange={(event) => updateField("preferred_language", event.target.value)}
              placeholder="en"
            />
            {errors.preferred_language ? <FieldError message={errors.preferred_language} /> : null}
          </Field>
          <Field label="Preferred locale">
            <input
              className={inputClassName(Boolean(errors.preferred_locale))}
              value={form.preferred_locale}
              onChange={(event) => updateField("preferred_locale", event.target.value)}
              placeholder="en-US"
            />
            {errors.preferred_locale ? <FieldError message={errors.preferred_locale} /> : null}
          </Field>
          <Field label="Retention window (days)">
            <input
              type="number"
              min={30}
              max={3650}
              className={inputClassName(Boolean(errors.data_retention_days))}
              value={form.data_retention_days}
              onChange={(event) => updateField("data_retention_days", Number(event.target.value))}
            />
            {errors.data_retention_days ? <FieldError message={errors.data_retention_days} /> : null}
          </Field>
          <Field label="AI memory handling">
            <label className="flex h-[50px] items-center gap-3 rounded-2xl border bg-white px-4 py-3 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={form.allow_ai_processing}
                onChange={(event) => updateField("allow_ai_processing", event.target.checked)}
              />
              Let Brivoly use AI to summarize relationship memory and draft notes.
            </label>
          </Field>
          <Field label="Privacy consent version">
            <input
              className={inputClassName(Boolean(errors.privacy_consent_version))}
              value={form.privacy_consent_version}
              onChange={(event) => updateField("privacy_consent_version", event.target.value)}
              placeholder="v1"
            />
            {errors.privacy_consent_version ? <FieldError message={errors.privacy_consent_version} /> : null}
            <p className="text-xs text-slate-500">
              {form.privacy_consent_granted_at
                ? `Consent last recorded ${new Date(form.privacy_consent_granted_at).toLocaleString()}.`
                : "Consent has not been recorded yet for this account."}
            </p>
          </Field>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button type="button" variant="outline" onClick={handlePrivacyExport}>
            Download account export
          </Button>
          <Button type="button" variant="outline" onClick={() => handlePrivacyErase("relationship_memory")}>
            Erase relationship memory
          </Button>
          <Button type="button" variant="outline" onClick={() => handlePrivacyErase("all_memory")}>
            Erase memory and mailbox links
          </Button>
          <p className="text-sm text-slate-500">Includes settings, connected mailboxes, and saved relationship memory.</p>
        </div>
      </section>

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={isPending} data-testid="settings-save-button">
          {isPending ? "Saving..." : "Save settings"}
        </Button>
        {status ? (
          <p className="text-sm text-slate-500" data-testid="settings-status">
            {status}
          </p>
        ) : null}
      </div>
    </form>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-2">
      <span className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">{label}</span>
      {children}
    </label>
  );
}

function FieldError({ message }: { message: string }) {
  return <p className="text-sm text-rose-600">{message}</p>;
}

function inputClassName(hasError: boolean) {
  return `w-full rounded-2xl border bg-white px-4 py-3 text-sm outline-none transition focus:border-primary ${
    hasError ? "border-rose-300" : ""
  }`;
}

function validateForm(form: AccountSettings) {
  const nextErrors: Partial<Record<keyof AccountSettings, string>> = {};
  if (!form.benchmark) {
    nextErrors.benchmark = "Benchmark is required.";
  }
  if (form.universe.length === 0) {
    nextErrors.universe = "Enter at least one universe symbol.";
  }
  if (!form.vix_symbol) {
    nextErrors.vix_symbol = "Fear gauge symbol is required.";
  }
  if (!form.risk_proxy) {
    nextErrors.risk_proxy = "Risk proxy symbol is required.";
  }
  if (!form.short_yield_symbol) {
    nextErrors.short_yield_symbol = "Short yield symbol is required.";
  }
  if (!form.long_yield_symbol) {
    nextErrors.long_yield_symbol = "Long yield symbol is required.";
  }
  if (form.lookback_years < 1 || form.lookback_years > 10) {
    nextErrors.lookback_years = "Lookback must be between 1 and 10 years.";
  }
  if (form.business_name.length > 160) {
    nextErrors.business_name = "Business name must be 160 characters or fewer.";
  }
  if (form.business_website.length > 255) {
    nextErrors.business_website = "Business website must be 255 characters or fewer.";
  }
  if (form.outbound_sender_name.length > 160) {
    nextErrors.outbound_sender_name = "Sender name must be 160 characters or fewer.";
  }
  if (form.business_logo_data_url.length > 700000) {
    nextErrors.business_logo_data_url = "Business logo payload is too large. Use a smaller image.";
  }
  if (form.crm_ai_prompt.length > 4000) {
    nextErrors.crm_ai_prompt = "AI prompt must be 4000 characters or fewer.";
  }
  if (form.crm_preferred_import_formats.length > 12) {
    nextErrors.crm_preferred_import_formats = "Keep preferred formats to 12 or fewer entries.";
  }
  if (form.crm_image_intake_channels.length > 12) {
    nextErrors.crm_image_intake_channels = "Keep image intake channels to 12 or fewer entries.";
  }
  if (form.crm_image_intake_notes.length > 1000) {
    nextErrors.crm_image_intake_notes = "Routing notes must be 1000 characters or fewer.";
  }
  if (form.profile_alias.length > 80) {
    nextErrors.profile_alias = "Alias must be 80 characters or fewer.";
  }
  if (!form.preferred_language || form.preferred_language.length > 16) {
    nextErrors.preferred_language = "Preferred language must be between 1 and 16 characters.";
  }
  if (!form.preferred_locale || form.preferred_locale.length > 24) {
    nextErrors.preferred_locale = "Preferred locale must be between 1 and 24 characters.";
  }
  if (form.data_retention_days < 30 || form.data_retention_days > 3650) {
    nextErrors.data_retention_days = "Retention window must be between 30 and 3650 days.";
  }
  if (!form.privacy_consent_version || form.privacy_consent_version.length > 32) {
    nextErrors.privacy_consent_version = "Consent version must be between 1 and 32 characters.";
  }
  return nextErrors;
}
