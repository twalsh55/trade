import { cookies } from "next/headers";

import { BRIVOLY_SESSION_COOKIE, LEGACY_TRADE_SESSION_COOKIE } from "@/lib/auth";
import {
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
  followUps: Awaited<ReturnType<typeof getCrmFollowUpOverview>> | null;
  accountSettings: Awaited<ReturnType<typeof getAccountSettings>> | null;
  billing: Awaited<ReturnType<typeof getBillingOverview>> | null;
  intakeChannel: Awaited<ReturnType<typeof getCrmRemoteIntakeChannel>> | null;
};

export async function loadCRMPageData(): Promise<CRMPageData> {
  const cookieStore = await cookies();
  const sessionToken =
    cookieStore.get(BRIVOLY_SESSION_COOKIE)?.value ?? cookieStore.get(LEGACY_TRADE_SESSION_COOKIE)?.value ?? null;
  const sessionCookie = cookieStore.get("__session")?.value;
  const cookieHeader = sessionCookie ? `__session=${sessionCookie}` : null;

  const [bootstrap, session] = await Promise.all([
    getSettingsBootstrap().catch(() => null),
    getSession({ sessionToken, cookieHeader }).catch(() => null),
  ]);

  const user = session?.user;
  const [followUps, accountSettings, billing, intakeChannel] = user
    ? await Promise.all([
        getCrmFollowUpOverview({ sessionToken, cookieHeader }).catch(() => null),
        getAccountSettings({ sessionToken, cookieHeader }).catch(() => null),
        getBillingOverview({ sessionToken, cookieHeader }).catch(() => null),
        getCrmRemoteIntakeChannel({ sessionToken, cookieHeader }).catch(() => null),
      ])
    : [null, null, null, null];

  return {
    bootstrap,
    session,
    user,
    userLabel: resolveUserDisplayName(user, accountSettings),
    followUps,
    accountSettings,
    billing,
    intakeChannel,
  };
}
