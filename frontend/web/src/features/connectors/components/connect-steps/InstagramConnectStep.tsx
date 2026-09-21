import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useNavigate } from "react-router-dom";
import { AxiosError } from "axios";
import { Instagram } from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input } from "@fusion-flow/ui";
import { useConnectConnector } from "../../hooks";

/**
 * Instagram's "connect" step: `auth_mode="api_key"`, same shape as
 * `WhatsAppConnectStep` - there is no shared platform Meta app and no OAuth
 * redirect. Each tenant generates their own access token in their own Meta
 * Business Suite (with instagram_basic, instagram_manage_messages,
 * instagram_manage_comments permissions) and pastes it here along with the
 * Instagram professional/business account id it belongs to. `app_secret` is
 * optional (it lets the backend verify inbound webhook signatures for this
 * specific instance - see `instagram/adapter.py`'s
 * `resolve_instance_for_webhook`); leaving it blank still connects, it just
 * means webhook verification falls back to a shared/global secret if one is
 * configured. `webhook_verify_token` is also optional and only matters if
 * the tenant registered their own separate Meta App's webhook subscription.
 */
const instagramSchema = z.object({
  instagram_account_id: z.string().min(1, "Instagram account ID is required"),
  access_token: z.string().min(1, "Access token is required"),
  app_secret: z.string().optional(),
  webhook_verify_token: z.string().optional(),
});

type InstagramFormValues = z.infer<typeof instagramSchema>;

export function InstagramConnectStep() {
  const navigate = useNavigate();
  const { mutate, isPending, error } = useConnectConnector();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<InstagramFormValues>({ resolver: zodResolver(instagramSchema) });

  function onSubmit(values: InstagramFormValues) {
    mutate(
      {
        typeKey: "instagram",
        payload: {
          params: {
            instagram_account_id: values.instagram_account_id,
            access_token: values.access_token,
            app_secret: values.app_secret || undefined,
            webhook_verify_token: values.webhook_verify_token || undefined,
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
          <Instagram className="h-7 w-7" />
        </div>
        <CardTitle>Connect Instagram Business Account</CardTitle>
        <CardDescription>
          Paste the credentials from your own Meta Business Suite. Your access token is encrypted
          at rest and is never shown again once saved.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="instagram_account_id" className="text-sm font-medium">
              Instagram account ID
            </label>
            <Input
              id="instagram_account_id"
              autoComplete="off"
              placeholder="Your Instagram professional/business account ID"
              error={!!errors.instagram_account_id}
              {...register("instagram_account_id")}
            />
            {errors.instagram_account_id && (
              <p className="text-xs text-destructive">{errors.instagram_account_id.message}</p>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="access_token" className="text-sm font-medium">
              Access token
            </label>
            <Input
              id="access_token"
              type="password"
              autoComplete="off"
              placeholder="A Page/User access token with instagram_manage_messages permissions"
              error={!!errors.access_token}
              {...register("access_token")}
            />
            {errors.access_token && (
              <p className="text-xs text-destructive">{errors.access_token.message}</p>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="app_secret" className="text-sm font-medium">
              App secret <span className="text-muted-foreground">(optional)</span>
            </label>
            <Input
              id="app_secret"
              type="password"
              autoComplete="off"
              placeholder="Verifies inbound webhook signatures for this connection"
              {...register("app_secret")}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="webhook_verify_token" className="text-sm font-medium">
              Webhook verify token <span className="text-muted-foreground">(optional)</span>
            </label>
            <Input
              id="webhook_verify_token"
              autoComplete="off"
              {...register("webhook_verify_token")}
            />
            <p className="text-xs text-muted-foreground">
              A verify token for your own Meta App&apos;s webhook subscription, if you&apos;re
              using one separate from the platform default.
            </p>
          </div>

          {mutationError && (
            <p className="text-sm text-destructive">
              {mutationError.response?.data?.detail ?? "Could not connect this Instagram account."}
            </p>
          )}

          <Button type="submit" disabled={isPending} className="mt-2">
            <Instagram className="h-4 w-4" />
            {isPending ? "Connecting…" : "Connect Instagram"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
