import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useNavigate, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { CheckCircle2 } from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input } from "@fusion-flow/ui";
import { signup } from "../lib/endpoints";
import { fetchSignupCatalog } from "../lib/signup-catalog-api";
import { AuthShell } from "../components/auth/AuthShell";

const signupSchema = z.object({
  business_name: z.string().min(2, "Business name is required"),
  email: z.string().email("Enter a valid email address"),
  password: z.string().min(8, "Password must be at least 8 characters"),
});

type SignupFormValues = z.infer<typeof signupSchema>;

/**
 * `/signup` — records an application for admin review, it does not create a
 * working session. The chosen starter-kit template (+ its vertical) and any
 * extra requested modules/connectors are submitted together with the
 * account, so an admin sees the whole request in one place - see
 * `POST /api/v1/auth/signup`'s new `SignupResult` response (no tokens) and
 * `GET /api/v1/business-templates/catalog` (the one unauthenticated
 * endpoint in the app, used to populate the pickers below).
 */
export function SignupPage() {
  const navigate = useNavigate();
  const [serverError, setServerError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
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
    formState: { errors },
  } = useForm<SignupFormValues>({ resolver: zodResolver(signupSchema) });

  function toggleExtraKey(key: string) {
    setExtraKeys((keys) => (keys.includes(key) ? keys.filter((k) => k !== key) : [...keys, key]));
  }

  async function onSubmit(values: SignupFormValues) {
    if (!templateId) {
      setTemplateError("Choose a starter kit to continue.");
      return;
    }
    setTemplateError(null);
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

  return (
    <AuthShell>
      <Card className="w-full max-w-2xl">
        <CardHeader>
          <CardTitle>Apply for a workspace</CardTitle>
          <CardDescription>
            Pick a starter kit and we'll set up your workspace once an admin approves your
            application.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="flex flex-col gap-6" onSubmit={handleSubmit(onSubmit)} noValidate>
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
            </div>

            <div className="flex flex-col gap-2">
              <p className="text-sm font-medium">Choose a starter kit</p>
              <p className="text-xs text-muted-foreground">
                A template bundles the connectors and custom fields a business like yours
                typically needs.
              </p>
              {catalogLoading && <p className="text-sm text-muted-foreground">Loading templates...</p>}
              {!catalogLoading && (catalog?.templates.length ?? 0) === 0 && (
                <p className="text-sm text-muted-foreground">No starter kits available yet.</p>
              )}
              <div className="flex flex-col gap-2">
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
                      className={
                        "flex items-center justify-between rounded-md border p-3 text-left transition-colors " +
                        (selected ? "border-accent bg-accent/5" : "border-border hover:border-accent/50")
                      }
                    >
                      <div>
                        <p className="text-sm font-medium text-foreground">{template.name}</p>
                        {template.description && (
                          <p className="text-xs text-muted-foreground">{template.description}</p>
                        )}
                        {template.connector_type_keys.length > 0 && (
                          <p className="text-xs text-muted-foreground">
                            Includes: {template.connector_type_keys.join(", ")}
                          </p>
                        )}
                      </div>
                      {selected && <CheckCircle2 className="h-4 w-4 shrink-0 text-accent" />}
                    </button>
                  );
                })}
              </div>
              {templateError && <p className="text-xs text-destructive">{templateError}</p>}
            </div>

            {extraCandidates.length > 0 && (
              <div className="flex flex-col gap-2">
                <p className="text-sm font-medium">Request additional modules/connectors (optional)</p>
                <p className="text-xs text-muted-foreground">
                  Anything outside your starter kit needs admin approval - request it now and it'll
                  be reviewed alongside your application.
                </p>
                <div className="flex flex-col gap-1.5">
                  {extraCandidates.map((c) => (
                    <label key={c.key} className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={extraKeys.includes(c.key)}
                        onChange={() => toggleExtraKey(c.key)}
                      />
                      {c.display_name}
                    </label>
                  ))}
                </div>
              </div>
            )}

            {serverError && <p className="text-sm text-destructive">{serverError}</p>}

            <Button type="submit" disabled={submitting} className="mt-2">
              {submitting ? "Submitting..." : "Submit application"}
            </Button>
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
