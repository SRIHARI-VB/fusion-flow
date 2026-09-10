import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useNavigate, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { ArrowLeft, ArrowRight, Check, Layers } from "lucide-react";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, cn } from "@fusion-flow/ui";
import { signup } from "../lib/endpoints";
import { fetchSignupCatalog } from "../lib/signup-catalog-api";
import { CONNECTOR_CATEGORY_ICON } from "../features/connectors/state-display";
import { AuthShell } from "../components/auth/AuthShell";

const signupSchema = z.object({
  business_name: z.string().min(2, "Business name is required"),
  email: z.string().email("Enter a valid email address"),
  password: z.string().min(8, "Password must be at least 8 characters"),
});

type SignupFormValues = z.infer<typeof signupSchema>;

type Step = "account" | "template" | "extras";
const STEPS: { key: Step; label: string }[] = [
  { key: "account", label: "Account" },
  { key: "template", label: "Starter kit" },
  { key: "extras", label: "Add-ons" },
];

/**
 * `/signup` — a 3-step application wizard: account details -> required
 * starter-kit template -> optional extra modules/connectors. Submitting
 * records an application for admin review, it does not create a working
 * session. The chosen template (+ its vertical) and any extra requested
 * modules/connectors are submitted together with the account, so an admin
 * sees the whole request in one place - see `POST /api/v1/auth/signup`'s
 * `SignupResult` response (no tokens) and `GET
 * /api/v1/business-templates/catalog` (the one unauthenticated endpoint in
 * the app, used to populate the pickers below).
 */
export function SignupPage() {
  const navigate = useNavigate();
  const [serverError, setServerError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [step, setStep] = useState<Step>("account");
  const [templateId, setTemplateId] = useState<string | null>(null);
  const [templateError, setTemplateError] = useState<string | null>(null);
  const [extraKeys, setExtraKeys] = useState<string[]>([]);

  const { data: catalog, isLoading: catalogLoading } = useQuery({
    queryKey: ["signup-catalog"],
    queryFn: fetchSignupCatalog,
  });

  const selectedTemplate = catalog?.templates.find((t) => t.id === templateId) ?? null;

  // Only offer connectors/modules not already bundled by the chosen
  // template - no point letting someone "extra request" what they'd get
  // for free the moment an admin approves them.
  const extraCandidates = useMemo(() => {
    const bundled = new Set(selectedTemplate?.connector_type_keys ?? []);
    return (catalog?.connector_types ?? []).filter((c) => !bundled.has(c.key));
  }, [catalog, selectedTemplate]);

  const {
    register,
    handleSubmit,
    trigger,
    formState: { errors },
  } = useForm<SignupFormValues>({ resolver: zodResolver(signupSchema) });

  function toggleExtraKey(key: string) {
    setExtraKeys((keys) => (keys.includes(key) ? keys.filter((k) => k !== key) : [...keys, key]));
  }

  async function goToTemplateStep() {
    const valid = await trigger(["business_name", "email", "password"]);
    if (valid) setStep("template");
  }

  function goToExtrasStep() {
    if (!templateId) {
      setTemplateError("Choose a starter kit to continue.");
      return;
    }
    setTemplateError(null);
    setStep("extras");
  }

  async function onSubmit(values: SignupFormValues) {
    if (!templateId) {
      setStep("template");
      setTemplateError("Choose a starter kit to continue.");
      return;
    }
    setServerError(null);
    setSubmitting(true);
    try {
      const result = await signup({
        ...values,
        vertical: selectedTemplate?.vertical ?? null,
        business_template_id: templateId,
        extra_connector_type_keys: extraKeys,
      });
      navigate("/application-submitted", { state: { businessName: result.business_name } });
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setServerError(
        axiosErr.response?.data?.detail ?? "Unable to create your account. Please try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  const activeIndex = STEPS.findIndex((s) => s.key === step);

  return (
    <AuthShell>
      <Card className="w-full max-w-2xl overflow-hidden">
        <CardHeader className="gap-4">
          <div>
            <CardTitle>Apply for a workspace</CardTitle>
            <CardDescription>
              Pick a starter kit and we&apos;ll set up your workspace once an admin approves your
              application.
            </CardDescription>
          </div>

          <div className="flex items-center justify-center gap-2 pt-1">
            {STEPS.map((s, i) => {
              const isActive = i === activeIndex;
              const isDone = i < activeIndex;
              return (
                <div key={s.key} className="flex items-center gap-2">
                  <div className="flex flex-col items-center gap-1">
                    <div
                      className={cn(
                        "flex h-8 w-8 items-center justify-center rounded-full border-2 text-xs font-semibold transition-colors",
                        isDone
                          ? "border-accent bg-accent text-accent-foreground"
                          : isActive
                            ? "border-accent text-accent"
                            : "border-border text-muted-foreground",
                      )}
                    >
                      {isDone ? <Check className="h-4 w-4" /> : i + 1}
                    </div>
                    <span
                      className={cn(
                        "text-[11px] font-medium",
                        isActive || isDone ? "text-foreground" : "text-muted-foreground",
                      )}
                    >
                      {s.label}
                    </span>
                  </div>
                  {i < STEPS.length - 1 && (
                    <div className={cn("mb-4 h-0.5 w-10 sm:w-16", isDone ? "bg-accent" : "bg-border")} />
                  )}
                </div>
              );
            })}
          </div>
        </CardHeader>

        <CardContent>
          <form className="flex flex-col gap-6" onSubmit={handleSubmit(onSubmit)} noValidate>
            {step === "account" && (
              <div className="flex flex-col gap-4">
                <div className="flex flex-col gap-1.5">
                  <label htmlFor="business_name" className="text-sm font-medium">
                    Business name
                  </label>
                  <Input
                    id="business_name"
                    placeholder="Acme Inc."
                    error={!!errors.business_name}
                    {...register("business_name")}
                  />
                  {errors.business_name && (
                    <p className="text-xs text-destructive">{errors.business_name.message}</p>
                  )}
                </div>

                <div className="flex flex-col gap-1.5">
                  <label htmlFor="email" className="text-sm font-medium">
                    Email
                  </label>
                  <Input
                    id="email"
                    type="email"
                    autoComplete="email"
                    placeholder="you@company.com"
                    error={!!errors.email}
                    {...register("email")}
                  />
                  {errors.email && <p className="text-xs text-destructive">{errors.email.message}</p>}
                </div>

                <div className="flex flex-col gap-1.5">
                  <label htmlFor="password" className="text-sm font-medium">
                    Password
                  </label>
                  <Input
                    id="password"
                    type="password"
                    autoComplete="new-password"
                    placeholder="••••••••"
                    error={!!errors.password}
                    {...register("password")}
                  />
                  {errors.password && <p className="text-xs text-destructive">{errors.password.message}</p>}
                </div>

                <Button type="button" className="mt-2" onClick={() => void goToTemplateStep()}>
                  Continue
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </div>
            )}

            {step === "template" && (
              <div className="flex flex-col gap-4">
                <div>
                  <p className="text-sm font-medium">Choose a starter kit</p>
                  <p className="text-xs text-muted-foreground">
                    A template bundles the connectors and custom fields a business like yours
                    typically needs.
                  </p>
                </div>

                {catalogLoading && <p className="text-sm text-muted-foreground">Loading templates...</p>}
                {!catalogLoading && (catalog?.templates.length ?? 0) === 0 && (
                  <p className="text-sm text-muted-foreground">No starter kits available yet.</p>
                )}

                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {catalog?.templates.map((template) => {
                    const selected = template.id === templateId;
                    return (
                      <button
                        type="button"
                        key={template.id}
                        onClick={() => {
                          setTemplateId(template.id);
                          setTemplateError(null);
                        }}
                        className={cn(
                          "relative flex flex-col gap-2 rounded-xl border-2 p-4 text-left transition-all hover:shadow-md",
                          selected
                            ? "border-accent bg-accent/5 shadow-md ring-2 ring-accent/20"
                            : "border-border hover:border-accent/50",
                        )}
                      >
                        {selected && (
                          <div className="absolute right-3 top-3 flex h-5 w-5 items-center justify-center rounded-full bg-accent text-accent-foreground">
                            <Check className="h-3 w-3" />
                          </div>
                        )}
                        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/10 text-accent">
                          <Layers className="h-4 w-4" />
                        </div>
                        <div>
                          <p className="text-sm font-semibold text-foreground">{template.name}</p>
                          {template.description && (
                            <p className="mt-0.5 text-xs text-muted-foreground">{template.description}</p>
                          )}
                        </div>
                        {template.connector_type_keys.length > 0 && (
                          <div className="flex flex-wrap gap-1 pt-1">
                            {template.connector_type_keys.map((key) => (
                              <Badge key={key} variant="secondary" className="text-[10px]">
                                {key}
                              </Badge>
                            ))}
                          </div>
                        )}
                      </button>
                    );
                  })}
                </div>
                {templateError && <p className="text-xs text-destructive">{templateError}</p>}

                <div className="mt-2 flex gap-2">
                  <Button type="button" variant="outline" onClick={() => setStep("account")}>
                    <ArrowLeft className="h-4 w-4" />
                    Back
                  </Button>
                  <Button type="button" onClick={goToExtrasStep}>
                    Continue
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            )}

            {step === "extras" && (
              <div className="flex flex-col gap-4">
                <div>
                  <p className="text-sm font-medium">Request additional modules/connectors</p>
                  <p className="text-xs text-muted-foreground">
                    Optional. Anything outside your starter kit needs admin approval - select any
                    you&apos;d like reviewed alongside your application.
                  </p>
                </div>

                {extraCandidates.length === 0 ? (
                  <p className="rounded-lg border border-dashed border-border p-4 text-center text-xs text-muted-foreground">
                    Your starter kit already includes everything in the catalog.
                  </p>
                ) : (
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                    {extraCandidates.map((c) => {
                      const selected = extraKeys.includes(c.key);
                      const Icon = CONNECTOR_CATEGORY_ICON[c.category];
                      return (
                        <button
                          type="button"
                          key={c.key}
                          onClick={() => toggleExtraKey(c.key)}
                          className={cn(
                            "relative flex flex-col items-center gap-2 rounded-xl border-2 p-3 text-center transition-all hover:shadow-md",
                            selected
                              ? "border-accent bg-accent/5 shadow-md ring-2 ring-accent/20"
                              : "border-border hover:border-accent/50",
                          )}
                        >
                          {selected && (
                            <div className="absolute right-2 top-2 flex h-4 w-4 items-center justify-center rounded-full bg-accent text-accent-foreground">
                              <Check className="h-3 w-3" />
                            </div>
                          )}
                          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/10 text-accent">
                            <Icon className="h-4 w-4" />
                          </div>
                          <p className="text-xs font-medium text-foreground">{c.display_name}</p>
                        </button>
                      );
                    })}
                  </div>
                )}

                {serverError && <p className="text-sm text-destructive">{serverError}</p>}

                <div className="mt-2 flex gap-2">
                  <Button type="button" variant="outline" onClick={() => setStep("template")}>
                    <ArrowLeft className="h-4 w-4" />
                    Back
                  </Button>
                  <Button type="submit" disabled={submitting}>
                    {submitting ? "Submitting..." : "Submit application"}
                  </Button>
                </div>
              </div>
            )}
          </form>

          <p className="mt-4 text-center text-sm text-muted-foreground">
            Already have an account?{" "}
            <Link to="/login" className="font-medium text-accent hover:underline">
              Sign in
            </Link>
          </p>
        </CardContent>
      </Card>
    </AuthShell>
  );
}
