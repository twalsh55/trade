import { CRMPortalPage } from "@/components/crm-portal-page";

export const dynamic = "force-dynamic";

export default async function CRMFollowUpsRoute() {
  return <CRMPortalPage view="followups" />;
}
