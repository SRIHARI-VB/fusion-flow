import { useState, type FormEvent, type ReactNode } from "react";
import { ShieldCheck } from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input } from "@fusion-flow/ui";
import type { Business } from "@fusion-flow/ts-types";
import { useAuthStore } from "../../lib/auth-store";
import { useStepUpAuth } from "../../lib/step-up-auth-store";

export interface RequireStepUpProps {
  children: ReactNode;
  /** Whether THIS logged-in membership needs to step up at all - e.g.
   * `(b) => !!b?.is_doctor` for the clinic-queue gate, `(b) => b?.role ===
   * "owner"` for the Settings gate. Anyone this returns false for passes
   * straight through with no prompt, every render (not just once) - the
   * gate is authoritative, not a one-time check. */
  when: (business: Business | null) => boolean;
  /** Shown on the password-confirmation card - explains WHY this specific
   * user is being asked, since the same generic gate now serves more than
   * one reason. */
  reason: string;
}

/**
 * Guards a sensitive area behind a fresh password confirmation, mirroring
 * `RequireModule`'s "wrap children, render a gate screen instead" shape.
 * Generic over WHO needs to step up (`when`) and WHY (`reason`) - e.g. a
 * doctor-flagged membership opening the clinic-queue board (protects
 * consultation notes), or an Owner opening Settings (confirms they're
 * genuinely the account that created this tenant, not just someone who
 * happens to know the login). Everyone `when` returns false for passes
 * straight through with no extra prompt. The backend independently
 * enforces its own equivalent checks server-side - this component is a
 * convenience gate, not the actual security boundary.
 */
export function RequireStepUp({ children, when, reason }: RequireStepUpProps) {
  const business = useAuthStore((s) => s.business);
  // Select the underlying token/expiry, not the `isValid` function itself -
  // that function reference never changes, so subscribing to it would never
  // trigger a re-render when `confirmPassword` succeeds and this component
  // would stay stuck showing the gate even after a valid token is stored.
  const token = useStepUpAuth((s) => s.token);
  const expiresAt = useStepUpAuth((s) => s.expiresAt);
  const isValid = useStepUpAuth((s) => s.isValid);

  if (!when(business)) {
    return <>{children}</>;
  }
  if (token && expiresAt && isValid()) {
    return <>{children}</>;
  }
  return <StepUpPasswordGate reason={reason} />;
}

function StepUpPasswordGate({ reason }: { reason: string }) {
  const [password, setPassword] = useState("");
  const confirmPassword = useStepUpAuth((s) => s.confirmPassword);
  const isConfirming = useStepUpAuth((s) => s.isConfirming);
  const error = useStepUpAuth((s) => s.error);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    try {
      await confirmPassword(password);
    } catch {
      // Error state already set on the store - nothing further to do here.
    }
  }

  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-4 py-16 text-center">
      <Card className="w-full text-left">
        <CardHeader className="items-center text-center">
          <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-accent-soft text-accent">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <CardTitle>Confirm your password to continue</CardTitle>
          <CardDescription>{reason}</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="step-up-password" className="text-sm font-medium">
                Password
              </label>
              <Input
                id="step-up-password"
                type="password"
                autoComplete="current-password"
                autoFocus
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                error={!!error}
              />
              {error && <p className="text-xs text-destructive">{error}</p>}
            </div>
            <Button type="submit" disabled={isConfirming || !password}>
              {isConfirming ? "Confirming…" : "Confirm"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
