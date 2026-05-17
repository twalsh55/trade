import { CRMPortalPage } from "@/components/crm-portal-page";

export const dynamic = "force-dynamic";

export default async function CRMIntakeRoute() {
  return <CRMPortalPage view="intake" />;
}
