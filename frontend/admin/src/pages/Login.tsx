import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useNavigate } from "react-router-dom";
import { AxiosError } from "axios";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Logo } from "@fusion-flow/ui";
import { login } from "../lib/endpoints";
import { useAuthStore } from "../lib/auth-store";
import { decodeAccessToken } from "../lib/jwt";

const loginSchema = z.object({
  email: z.string().email("Enter a valid email address"),
  password: z.string().min(8, "Password must be at least 8 characters"),
});

type LoginFormValues = z.infer<typeof loginSchema>;

export function LoginPage() {
  const navigate = useNavigate();
  const setSession = useAuthStore((s) => s.setSession);
  const [serverError, setServerError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormValues>({ resolver: zodResolver(loginSchema) });

  async function onSubmit(values: LoginFormValues) {
    setServerError(null);
    setSubmitting(true);
    try {
      const session = await login(values);
      const claims = decodeAccessToken(session.access_token);

      // Platform-admin gate: the super-admin app must never proceed past login for a token
      // that doesn't carry `platform_admin: true`, even if the credentials themselves were
      // valid — this is a distinct, tenant-scoped user in that case.
      if (!claims.platform_admin) {
        setServerError("This account does not have platform-admin access.");
        return;
      }

      setSession(session);
      navigate("/tenants");
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setServerError(
        axiosErr.response?.data?.detail ?? "Unable to sign in. Check your credentials and try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-8 bg-background px-4">
      <div className="flex items-center gap-2">
        <Logo size={36} />
        <span className="text-lg font-semibold text-foreground">fusion-flow admin</span>
      </div>

      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Platform admin sign in</CardTitle>
          <CardDescription>Restricted to platform-admin accounts only.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="email" className="text-sm font-medium">
                Email
              </label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                placeholder="admin@fusion-flow.com"
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
                autoComplete="current-password"
                placeholder="••••••••"
                error={!!errors.password}
                {...register("password")}
              />
              {errors.password && <p className="text-xs text-destructive">{errors.password.message}</p>}
            </div>

            {serverError && <p className="text-sm text-destructive">{serverError}</p>}

            <Button type="submit" disabled={submitting} className="mt-2">
              {submitting ? "Signing in..." : "Sign in"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
