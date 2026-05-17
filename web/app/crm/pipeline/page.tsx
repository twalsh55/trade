import { CRMPortalPage } from "@/components/crm-portal-page";

export const dynamic = "force-dynamic";

export default async function CRMPipelineRoute() {
  return <CRMPortalPage view="pipeline" />;
}
