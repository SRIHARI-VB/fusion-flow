import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useNavigate } from "react-router-dom";
import { AxiosError } from "axios";
import { HardDrive } from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input } from "@fusion-flow/ui";
import { useConnectConnector } from "../../hooks";

/**
 * Cloudflare R2's "connect" step: `auth_mode="api_key"` (see
 * `backend/.../connectors/cloudflare_r2/adapter.py::CONFIG_SCHEMA`), same
 * shape family as `RazorpayConnectStep.tsx` - no OAuth redirect, the
 * tenant pastes an R2 API token generated in their own Cloudflare
 * dashboard (R2 → Manage API Tokens) directly into this form. This is a
 * tenant-owned storage bucket, not a platform-provided one - every
 * uploaded file (message media, template headers) lands in the tenant's
 * own R2 account.
 */
const r2Schema = z.object({
  account_id: z.string().min(1, "Account ID is required"),
  access_key_id: z.string().min(1, "Access key ID is required"),
  secret_access_key: z.string().min(1, "Secret access key is required"),
  bucket_name: z.string().min(1, "Bucket name is required"),
  endpoint_url: z.string().optional(),
});

type CloudflareR2FormValues = z.infer<typeof r2Schema>;

export function CloudflareR2ConnectStep() {
  const navigate = useNavigate();
  const { mutate, isPending, error } = useConnectConnector();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<CloudflareR2FormValues>({ resolver: zodResolver(r2Schema) });

  function onSubmit(values: CloudflareR2FormValues) {
    mutate(
      {
        typeKey: "cloudflare_r2",
        payload: {
          params: {
            account_id: values.account_id,
            access_key_id: values.access_key_id,
            secret_access_key: values.secret_access_key,
            bucket_name: values.bucket_name,
            endpoint_url: values.endpoint_url || undefined,
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
          <HardDrive className="h-7 w-7" />
        </div>
        <CardTitle>Connect Cloudflare R2</CardTitle>
        <CardDescription>
          Paste an R2 API token from your own Cloudflare dashboard (R2 → Manage API Tokens) and the bucket
          to store uploads in. Your secret access key is encrypted at rest and is never shown again once
          saved.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="account_id" className="text-sm font-medium">
              Account ID
            </label>
            <Input
              id="account_id"
              autoComplete="off"
              error={!!errors.account_id}
              {...register("account_id")}
            />
            {errors.account_id && <p className="text-xs text-destructive">{errors.account_id.message}</p>}
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="access_key_id" className="text-sm font-medium">
              Access Key ID
            </label>
            <Input
              id="access_key_id"
              autoComplete="off"
              error={!!errors.access_key_id}
              {...register("access_key_id")}
            />
            {errors.access_key_id && (
              <p className="text-xs text-destructive">{errors.access_key_id.message}</p>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="secret_access_key" className="text-sm font-medium">
              Secret Access Key
            </label>
            <Input
              id="secret_access_key"
              type="password"
              autoComplete="off"
              error={!!errors.secret_access_key}
              {...register("secret_access_key")}
            />
            {errors.secret_access_key && (
              <p className="text-xs text-destructive">{errors.secret_access_key.message}</p>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="bucket_name" className="text-sm font-medium">
              Bucket name
            </label>
            <Input
              id="bucket_name"
              autoComplete="off"
              error={!!errors.bucket_name}
              {...register("bucket_name")}
            />
            {errors.bucket_name && <p className="text-xs text-destructive">{errors.bucket_name.message}</p>}
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="endpoint_url" className="text-sm font-medium">
              Endpoint URL <span className="text-muted-foreground">(optional)</span>
            </label>
            <Input
              id="endpoint_url"
              autoComplete="off"
              placeholder="Defaults to https://{account_id}.r2.cloudflarestorage.com"
              {...register("endpoint_url")}
            />
          </div>

          {mutationError && (
            <p className="text-sm text-destructive">
              {mutationError.response?.data?.detail ?? "Could not connect this Cloudflare R2 bucket."}
            </p>
          )}

          <Button type="submit" disabled={isPending} className="mt-2">
            <HardDrive className="h-4 w-4" />
            {isPending ? "Connecting…" : "Connect Cloudflare R2"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
