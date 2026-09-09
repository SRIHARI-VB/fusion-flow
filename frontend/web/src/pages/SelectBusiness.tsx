import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { Business } from "@fusion-flow/ts-types";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@fusion-flow/ui";
import { fetchMyBusinesses, selectBusiness } from "../lib/endpoints";
import { useAuthStore } from "../lib/auth-store";
import { AuthShell } from "../components/auth/AuthShell";

/**
 * Shown when a login response has no resolved tenant (multi-membership "pre-tenant" token).
 * Lists the user's businesses via GET /businesses/mine and lets them pick one, then calls
 * POST /businesses/{id}/switch (or /auth/select-business) to mint full tenant-scoped claims.
 */
export function SelectBusinessPage() {
  const navigate = useNavigate();
  const setSession = useAuthStore((s) => s.setSession);
  const accessToken = useAuthStore((s) => s.accessToken);
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectingId, setSelectingId] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) {
      navigate("/login");
      return;
    }
    fetchMyBusinesses()
      .then(setBusinesses)
      .catch(() => setError("Could not load your businesses. Please sign in again."))
      .finally(() => setLoading(false));
  }, [accessToken, navigate]);

  async function handleSelect(businessId: string) {
    setSelectingId(businessId);
    setError(null);
    try {
      const session = await selectBusiness(businessId);
      setSession(session);
      navigate("/dashboard");
    } catch {
      setError("Could not switch to that business. Please try again.");
    } finally {
      setSelectingId(null);
    }
  }

  return (
    <AuthShell>
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Choose a workspace</CardTitle>
          <CardDescription>You belong to more than one business — pick one to continue.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {loading && <p className="text-sm text-muted-foreground">Loading your businesses...</p>}
          {error && <p className="text-sm text-destructive">{error}</p>}

          {!loading &&
            businesses.map((business) => (
              <Button
                key={business.id}
                variant="outline"
                className="justify-between"
                disabled={selectingId !== null}
                onClick={() => handleSelect(business.id)}
              >
                <span>{business.name}</span>
                <span className="text-xs text-muted-foreground">
                  {selectingId === business.id ? "Switching..." : business.slug}
                </span>
              </Button>
            ))}

          {!loading && businesses.length === 0 && !error && (
            <p className="text-sm text-muted-foreground">No businesses found for this account.</p>
          )}
        </CardContent>
      </Card>
    </AuthShell>
  );
}
