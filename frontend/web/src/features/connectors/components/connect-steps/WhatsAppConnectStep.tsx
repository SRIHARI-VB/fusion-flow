import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useNavigate } from "react-router-dom";
import { AxiosError } from "axios";
import { MessageCircle } from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input } from "@fusion-flow/ui";
import { useConnectConnector } from "../../hooks";

/**
 * WhatsApp's "connect" step: `auth_mode="api_key"`, same shape as
 * `RazorpayConnectStep` - there is no shared platform Meta app and no OAuth
 * redirect. Each tenant generates their own permanent access token in their
 * own Meta Business Manager (WhatsApp > API Setup) and pastes it here along
 * with their Phone Number ID. The WhatsApp Business Account ID is
 * deliberately not asked for - the backend derives it from the phone
 * number ID itself during validation (one less id to copy/paste wrong).
 * `app_secret` is optional (it lets the backend verify inbound webhook
 * signatures for this specific instance - see `whatsapp/adapter.py`'s
 * `resolve_instance_for_webhook`); leaving it blank still connects, it
 * just means webhook verification falls back to a shared/global secret if
 * one is configured.
 */
const whatsappSchema = z.object({
  access_token: z.string().min(1, "Access token is required"),
  phone_number_id: z.string().min(1, "Phone Number ID is required"),
  app_secret: z.string().optional(),
});

type WhatsAppFormValues = z.infer<typeof whatsappSchema>;

export function WhatsAppConnectStep() {
  const navigate = useNavigate();
  const { mutate, isPending, error } = useConnectConnector();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<WhatsAppFormValues>({ resolver: zodResolver(whatsappSchema) });

  function onSubmit(values: WhatsAppFormValues) {
    mutate(
      {
        typeKey: "whatsapp",
        payload: {
          params: {
            access_token: values.access_token,
            phone_number_id: values.phone_number_id,
            app_secret: values.app_secret || undefined,
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
          <MessageCircle className="h-7 w-7" />
        </div>
        <CardTitle>Connect WhatsApp Business Account</CardTitle>
        <CardDescription>
          Paste the credentials from your own Meta Business Manager (WhatsApp → API Setup). Your
          access token is encrypted at rest and is never shown again once saved.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="access_token" className="text-sm font-medium">
              Access token
            </label>
            <Input
              id="access_token"
              type="password"
              autoComplete="off"
              placeholder="A permanent System User access token"
              error={!!errors.access_token}
              {...register("access_token")}
            />
            {errors.access_token && (
              <p className="text-xs text-destructive">{errors.access_token.message}</p>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="phone_number_id" className="text-sm font-medium">
              Phone Number ID
            </label>
            <Input
              id="phone_number_id"
              autoComplete="off"
              error={!!errors.phone_number_id}
              {...register("phone_number_id")}
            />
            {errors.phone_number_id && (
              <p className="text-xs text-destructive">{errors.phone_number_id.message}</p>
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

          {mutationError && (
            <p className="text-sm text-destructive">
              {mutationError.response?.data?.detail ?? "Could not connect this WhatsApp account."}
            </p>
          )}

          <Button type="submit" disabled={isPending} className="mt-2">
            <MessageCircle className="h-4 w-4" />
            {isPending ? "Connecting…" : "Connect WhatsApp"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
