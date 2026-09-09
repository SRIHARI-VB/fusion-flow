import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { CheckCircle2, Plug, SkipForward } from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input } from "@fusion-flow/ui";
import { useAuthStore } from "../../lib/auth-store";
import { applyFieldTemplate, listFieldTemplates } from "../custom-fields";
import { updateBusiness } from "./api";

const VERTICALS = [
  { value: "retail", label: "Retail" },
  { value: "salon", label: "Salon & Beauty" },
  { value: "restaurant", label: "Restaurant" },
  { value: "other", label: "Other" },
];

const businessSchema = z.object({
  name: z.string().min(1, "Business name is required"),
  vertical: z.string().min(1, "Choose a vertical"),
});
type BusinessFormValues = z.infer<typeof businessSchema>;

type Step = "business" | "template" | "connect" | "finish";
const STEPS: { key: Step; label: string }[] = [
  { key: "business", label: "Business" },
  { key: "template", label: "Custom fields" },
  { key: "connect", label: "Connect" },
  { key: "finish", label: "Finish" },
];

/**
 * `/onboarding` — business info -> apply a custom-fields template (or skip)
 * -> optional "connect a connector" step -> finish -> `/dashboard`.
 *
 * Uses the JWT's `tenant_id` claim (not `auth-store`'s `business` field) as
 * the active business id: signup always mints a fully tenant-scoped token
 * directly (single membership, no select-business step - see SignupPage),
 * so `claims.tenant_id` is guaranteed to be the freshly created business
 * the moment this page mounts.
 */
export function OnboardingPage() {
  const navigate = useNavigate();
  const claims = useAuthStore((s) => s.claims);
  const business = useAuthStore((s) => s.business);
  const setBusiness = useAuthStore((s) => s.setBusiness);
  const businessId = claims?.tenant_id ?? null;

  const [step, setStep] = useState<Step>("business");
  const [vertical, setVertical] = useState<string>(business?.vertical ?? "");
  const [appliedTemplateIds, setAppliedTemplateIds] = useState<string[]>([]);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<BusinessFormValues>({
    resolver: zodResolver(businessSchema),
    defaultValues: { name: business?.name ?? "", vertical: business?.vertical ?? "" },
  });

  const businessMutation = useMutation({
    mutationFn: (values: BusinessFormValues) => {
      if (!businessId) throw new Error("No active business on this session");
      return updateBusiness(businessId, { name: values.name, vertical: values.vertical });
    },
    onSuccess: (updated) => {
      setBusiness(updated);
      setVertical(updated.vertical ?? "");
      setStep("template");
    },
  });

  const { data: templates = [], isLoading: templatesLoading } = useQuery({
    queryKey: ["custom-fields", "templates", vertical],
    queryFn: () => listFieldTemplates({ vertical }),
    enabled: step === "template" && !!vertical,
  });

  const applyMutation = useMutation({
    mutationFn: (templateId: string) => applyFieldTemplate(templateId),
    onSuccess: (_result, templateId) => setAppliedTemplateIds((ids) => [...ids, templateId]),
  });

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
        <h1 className="text-2xl font-semibold text-foreground">Welcome to fusion-flow</h1>
        <p className="text-sm text-muted-foreground">A few quick steps to set up your workspace.</p>
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

      {step === "business" && (
        <Card>
          <CardHeader>
            <CardTitle>Tell us about your business</CardTitle>
            <CardDescription>This drives which custom-field templates we suggest.</CardDescription>
          </CardHeader>
          <CardContent>
            <form
              className="flex flex-col gap-4"
              onSubmit={handleSubmit((values) => businessMutation.mutate(values))}
              noValidate
            >
              <div className="flex flex-col gap-1.5">
                <label htmlFor="name" className="text-sm font-medium">
                  Business name
                </label>
                <Input id="name" error={!!errors.name} {...register("name")} />
                {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="vertical" className="text-sm font-medium">
                  Vertical
                </label>
                <select
                  id="vertical"
                  className="flex h-10 w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  defaultValue={business?.vertical ?? ""}
                  {...register("vertical")}
                >
                  <option value="" disabled>
                    Select a vertical...
                  </option>
                  {VERTICALS.map((v) => (
                    <option key={v.value} value={v.value}>
                      {v.label}
                    </option>
                  ))}
                </select>
                {errors.vertical && <p className="text-xs text-destructive">{errors.vertical.message}</p>}
              </div>
              {businessMutation.isError && (
                <p className="text-sm text-destructive">Could not save your business. Please try again.</p>
              )}
              <Button type="submit" disabled={businessMutation.isPending}>
                {businessMutation.isPending ? "Saving..." : "Continue"}
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      {step === "template" && (
        <Card>
          <CardHeader>
            <CardTitle>Apply a starter custom-fields template</CardTitle>
            <CardDescription>
              Templates add ready-made fields (e.g. SKU, stock quantity) to your products/services/coupons/
              offers. You can add more later from your catalog pages.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {templatesLoading && <p className="text-sm text-muted-foreground">Loading templates...</p>}
            {!templatesLoading && templates.length === 0 && (
              <p className="text-sm text-muted-foreground">No templates available for this vertical yet.</p>
            )}
            {templates.map((template) => {
              const applied = appliedTemplateIds.includes(template.id);
              return (
                <div
                  key={template.id}
                  className="flex items-center justify-between rounded-md border border-border p-3"
                >
                  <div>
                    <p className="text-sm font-medium text-foreground">{template.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {template.entity_type} - {template.fields.length} field(s)
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant={applied ? "outline" : "default"}
                    disabled={applied || applyMutation.isPending}
                    onClick={() => applyMutation.mutate(template.id)}
                  >
                    {applied ? (
                      <>
                        <CheckCircle2 className="h-4 w-4" />
                        Applied
                      </>
                    ) : (
                      "Apply"
                    )}
                  </Button>
                </div>
              );
            })}

            <div className="mt-2 flex gap-2">
              <Button onClick={() => setStep("connect")}>Continue</Button>
              <Button variant="outline" onClick={() => setStep("connect")}>
                <SkipForward className="h-4 w-4" />
                Skip
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

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
