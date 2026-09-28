import { useState, type FormEvent, type ReactNode } from "react";
import { ShieldCheck } from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input } from "@fusion-flow/ui";
import { useAuthStore } from "../../lib/auth-store";
import { useStepUpAuth } from "../../lib/step-up-auth-store";

/**
 * Guards the clinic-queue module's doctor-only actions behind a fresh
 * password confirmation, mirroring `RequireModule`'s "wrap children, render
 * a gate screen instead" shape. Only applies to a doctor-flagged membership
 * (`business.is_doctor`) - receptionist/owner access falls straight through
 * with no extra prompt, since this gate exists to protect what a DOCTOR sees
 * (consultation notes), not the module as a whole. The backend also enforces
 * notes-visibility server-side independent of this - this component is a
 * convenience gate, not the actual security boundary.
 */
export function RequireStepUp({ children }: { children: ReactNode }) {
  const business = useAuthStore((s) => s.business);
  const isValid = useStepUpAuth((s) => s.isValid);

  if (!business?.is_doctor) {
    return <>{children}</>;
  }
  if (isValid()) {
    return <>{children}</>;
  }
  return <StepUpPasswordGate />;
}

function StepUpPasswordGate() {
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
          <CardDescription>
            The Patient Flow board includes consultation notes only doctors can see - please
            re-enter your password to continue.
          </CardDescription>
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
