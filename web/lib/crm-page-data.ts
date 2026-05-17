import { cookies } from "next/headers";

import { BRIVOLY_SESSION_COOKIE, LEGACY_TRADE_SESSION_COOKIE } from "@/lib/auth";
import {
  ApiError,
  getAccountSettings,
  getBillingOverview,
  getCrmFollowUpOverview,
  getCrmRemoteIntakeChannel,
  getSession,
  getSettingsBootstrap,
} from "@/lib/api";
import { resolveUserDisplayName } from "@/lib/user-display";

export type CRMPageData = {
  bootstrap: Awaited<ReturnType<typeof getSettingsBootstrap>> | null;
  session: Awaited<ReturnType<typeof getSession>> | null;
  user: Awaited<ReturnType<typeof getSession>>["user"] | null | undefined;
  userLabel: string | null;
  loadErrors: string[];
  followUps: Awaited<ReturnType<typeof getCrmFollowUpOverview>> | null;
  accountSettings: Awaited<ReturnType<typeof getAccountSettings>> | null;
  billing: Awaited<ReturnType<typeof getBillingOverview>> | null;
  intakeChannel: Awaited<ReturnType<typeof getCrmRemoteIntakeChannel>> | null;
};

export async function loadCRMPageData(): Promise<CRMPageData> {
  const loadErrors: string[] = [];
  const cookieStore = await cookies();
  const sessionToken =
    cookieStore.get(BRIVOLY_SESSION_COOKIE)?.value ?? cookieStore.get(LEGACY_TRADE_SESSION_COOKIE)?.value ?? null;
  const sessionCookie = cookieStore.get("__session")?.value;
  const cookieHeader = sessionCookie ? `__session=${sessionCookie}` : null;

  const [bootstrap, session] = await Promise.all([
    getSettingsBootstrap().catch((error: unknown) => {
      loadErrors.push(formatCRMPageError(error, "Unable to load app bootstrap."));
      return null;
    }),
    getSession({ sessionToken, cookieHeader }).catch((error: unknown) => {
      loadErrors.push(formatCRMPageError(error, "Unable to verify the current session."));
      return null;
    }),
  ]);

  const user = session?.user;
  const [followUps, accountSettings, billing, intakeChannel] = await Promise.all([
    getCrmFollowUpOverview({ sessionToken, cookieHeader }).catch((error: unknown) => {
      loadErrors.push(formatCRMPageError(error, "Unable to load relationship data."));
      return null;
    }),
    getAccountSettings({ sessionToken, cookieHeader }).catch((error: unknown) => {
      loadErrors.push(formatCRMPageError(error, "Unable to load account settings."));
      return null;
    }),
    getBillingOverview({ sessionToken, cookieHeader }).catch((error: unknown) => {
      loadErrors.push(formatCRMPageError(error, "Unable to load billing status."));
      return null;
    }),
    getCrmRemoteIntakeChannel({ sessionToken, cookieHeader }).catch((error: unknown) => {
      loadErrors.push(formatCRMPageError(error, "Unable to load dropzone settings."));
      return null;
    }),
  ]);

  return {
    bootstrap,
    session,
    user,
    userLabel: resolveUserDisplayName(user, accountSettings),
    loadErrors,
    followUps,
    accountSettings,
    billing,
    intakeChannel,
  };
}

function formatCRMPageError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return error.message || fallback;
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message.trim();
  }
  return fallback;
}
