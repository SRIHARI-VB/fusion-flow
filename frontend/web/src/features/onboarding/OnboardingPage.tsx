import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { Plug, SkipForward } from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@fusion-flow/ui";
import { useAuthStore } from "../../lib/auth-store";
import { updateBusiness } from "./api";

type Step = "connect" | "finish";
const STEPS: { key: Step; label: string }[] = [
  { key: "connect", label: "Connect" },
  { key: "finish", label: "Finish" },
];

/**
 * `/onboarding` — optional "connect a connector" step -> finish -> `/dashboard`.
 *
 * Business name/vertical and the starter-kit template are now chosen at
 * signup and applied server-side when an admin approves the application
 * (see `pages/Signup.tsx` and `modules.admin.service.approve_tenant`), so
 * by the time this page can even be reached (it requires a working
 * session, which only exists post-approval) that work is already done.
 * All that's left here is the "connect your first channel" step, since
 * OAuth genuinely needs a live session to redirect through.
 *
 * Uses the JWT's `tenant_id` claim (not `auth-store`'s `business` field) as
 * the active business id, matching the rest of this app's convention.
 */
export function OnboardingPage() {
  const navigate = useNavigate();
  const claims = useAuthStore((s) => s.claims);
  const setBusiness = useAuthStore((s) => s.setBusiness);
  const businessId = claims?.tenant_id ?? null;

  const [step, setStep] = useState<Step>("connect");

  const finishMutation = useMutation({
    mutationFn: () => {
      if (!businessId) throw new Error("No active business on this session");
      return updateBusiness(businessId, { mark_onboarding_complete: true });
    },
    onSuccess: (updated) => {
      setBusiness(updated);
      navigate("/dashboard");
    },
  });

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 py-8">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Welcome to Stilltyping</h1>
        <p className="text-sm text-muted-foreground">A couple more steps and you're set up.</p>
      </div>

      <ol className="flex flex-wrap gap-2 text-xs font-medium text-muted-foreground">
        {STEPS.map((s, i) => (
          <li
            key={s.key}
            className={
              "flex items-center gap-1 rounded-full border px-3 py-1 " +
              (s.key === step ? "border-accent text-accent" : "border-border")
            }
          >
            {i + 1}. {s.label}
          </li>
        ))}
      </ol>

      {step === "connect" && (
        <Card>
          <CardHeader>
            <CardTitle>Connect your first channel</CardTitle>
            <CardDescription>
              Hook up WhatsApp, Razorpay, or another connector now, or do it later from Connectors.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <Link to="/connectors" className="inline-flex w-fit">
              <Button variant="outline">
                <Plug className="h-4 w-4" />
                Go to Connectors
              </Button>
            </Link>
            <div className="flex gap-2">
              <Button onClick={() => setStep("finish")}>Continue</Button>
              <Button variant="outline" onClick={() => setStep("finish")}>
                <SkipForward className="h-4 w-4" />
                Skip
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === "finish" && (
        <Card>
          <CardHeader>
            <CardTitle>You're all set</CardTitle>
            <CardDescription>Finish onboarding and head to your dashboard.</CardDescription>
          </CardHeader>
          <CardContent>
            {finishMutation.isError && (
              <p className="mb-3 text-sm text-destructive">Could not finish onboarding. Please try again.</p>
            )}
            <Button onClick={() => finishMutation.mutate()} disabled={finishMutation.isPending}>
              {finishMutation.isPending ? "Finishing..." : "Go to dashboard"}
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
