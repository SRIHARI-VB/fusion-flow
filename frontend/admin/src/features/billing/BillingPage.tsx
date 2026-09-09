import { useQuery } from "@tanstack/react-query";
import { Wallet } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@fusion-flow/ui";
import { fetchBillingUsage } from "../../lib/endpoints";

export function BillingPage() {
  const { data, isLoading } = useQuery({ queryKey: ["admin", "billing-usage"], queryFn: fetchBillingUsage });

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Billing &amp; usage</h1>
        <p className="text-sm text-muted-foreground">
          Metering/billing is Phase 2+ per the roadmap. This is a placeholder view only.
        </p>
      </div>

      <Card>
        <CardHeader className="items-center text-center">
          <div className="mb-2 flex h-12 w-12 items-center justify-center rounded-full bg-accent-soft text-accent">
            <Wallet className="h-6 w-6" />
          </div>
          <CardTitle>Not implemented yet</CardTitle>
          <CardDescription>
            {isLoading
              ? "Loading…"
              : data?.reason ?? "Billing/usage metering is not implemented yet."}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex justify-center py-6 text-sm text-muted-foreground">
          {!isLoading && data && <span>{data.tenants_count} tenants on the platform today.</span>}
        </CardContent>
      </Card>
    </div>
  );
}
