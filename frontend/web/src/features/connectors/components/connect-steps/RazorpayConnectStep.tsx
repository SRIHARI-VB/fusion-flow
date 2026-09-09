import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useNavigate } from "react-router-dom";
import { AxiosError } from "axios";
import { CreditCard } from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input } from "@fusion-flow/ui";
import { useConnectConnector } from "../../hooks";

/**
 * Razorpay's "connect" step: `auth_mode="api_key"`, so there is no OAuth
 * redirect - the tenant pastes the key pair generated in their own
 * Razorpay dashboard directly into this form. `webhook_secret` is
 * optional (it lets the backend verify `X-Razorpay-Signature` for this
 * specific instance - see `razorpay/adapter.py`'s
 * `resolve_instance_for_webhook`); leaving it blank still connects, it
 * just means webhook verification falls back to a shared/global secret.
 */
const razorpaySchema = z.object({
  key_id: z.string().min(1, "Key ID is required"),
  key_secret: z.string().min(1, "Key secret is required"),
  webhook_secret: z.string().optional(),
});

type RazorpayFormValues = z.infer<typeof razorpaySchema>;

export function RazorpayConnectStep() {
  const navigate = useNavigate();
  const { mutate, isPending, error } = useConnectConnector();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<RazorpayFormValues>({ resolver: zodResolver(razorpaySchema) });

  function onSubmit(values: RazorpayFormValues) {
    mutate(
      {
        typeKey: "razorpay",
        payload: {
          params: {
            key_id: values.key_id,
            key_secret: values.key_secret,
            webhook_secret: values.webhook_secret || undefined,
          },
        },
      },
      {
        onSuccess: (response) => navigate(`/connectors/${response.instance.id}?connected=1`),
      },
    );
  }

  const mutationError = error as AxiosError<{ detail?: string }> | null;

  return (
    <Card className="mx-auto max-w-lg">
      <CardHeader className="items-center text-center">
        <div className="mb-2 flex h-14 w-14 items-center justify-center rounded-full bg-accent-soft text-accent">
          <CreditCard className="h-7 w-7" />
        </div>
        <CardTitle>Connect Razorpay</CardTitle>
        <CardDescription>
          Paste the API key pair from your Razorpay dashboard (Settings → API Keys). Your key secret is
          encrypted at rest and is never shown again once saved.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="key_id" className="text-sm font-medium">
              Key ID
            </label>
            <Input
              id="key_id"
              placeholder="rzp_test_XXXXXXXXXXXXXX"
              autoComplete="off"
              error={!!errors.key_id}
              {...register("key_id")}
            />
            {errors.key_id && <p className="text-xs text-destructive">{errors.key_id.message}</p>}
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="key_secret" className="text-sm font-medium">
              Key Secret
            </label>
            <Input
              id="key_secret"
              type="password"
              autoComplete="off"
              error={!!errors.key_secret}
              {...register("key_secret")}
            />
            {errors.key_secret && <p className="text-xs text-destructive">{errors.key_secret.message}</p>}
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="webhook_secret" className="text-sm font-medium">
              Webhook secret <span className="text-muted-foreground">(optional)</span>
            </label>
            <Input
              id="webhook_secret"
              type="password"
              autoComplete="off"
              placeholder="Configured on the webhook you add in Razorpay's dashboard"
              {...register("webhook_secret")}
            />
          </div>

          {mutationError && (
            <p className="text-sm text-destructive">
              {mutationError.response?.data?.detail ?? "Could not connect this Razorpay account."}
            </p>
          )}

          <Button type="submit" disabled={isPending} className="mt-2">
            <CreditCard className="h-4 w-4" />
            {isPending ? "Connecting…" : "Connect Razorpay"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
