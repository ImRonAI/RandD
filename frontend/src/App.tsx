import { useEffect, useState } from "react";
import { PageState } from "@/vantage/components";
import { VantageAgentFrame } from "@/vantage";
import { vantageApi } from "@/vantage/api/client";
import { MagicCodeSignIn, OrganizationChooser } from "@/vantage/screens/AuthScreens";
import type { Organization, UserSession } from "@/vantage/types";

/**
 * Production Vantage entry point. Authentication and organization scope come
 * from the canonical FastAPI session; the persistent agent owns the field UI.
 */
export default function App() {
  const reviewMode = (import.meta as ImportMeta & { env: { DEV: boolean } }).env.DEV && new URLSearchParams(location.search).get("review") === "agent-frame";
  const [session, setSession] = useState<UserSession | null>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    if (reviewMode) {
      setChecking(false);
      return;
    }
    void vantageApi.me().then((result) => {
      if (result.ok) setSession(result.data);
      setChecking(false);
    });
  }, [reviewMode]);

  if (reviewMode) return <VantageAgentFrame />;

  if (checking) {
    return <main className="v-app"><PageState kind="loading" title="Opening Vantage" detail="Verifying your secure session." /></main>;
  }
  if (!session) return <MagicCodeSignIn onAuthenticated={setSession} />;
  if (!session.activeOrganizationId) {
    return <OrganizationChooser organizations={session.organizations} onChoose={async (organization: Organization) => {
      const result = await vantageApi.chooseOrganization(organization.id);
      if (result.ok) setSession({ ...session, activeOrganizationId: organization.id });
    }} />;
  }
  return <VantageAgentFrame />;
}
