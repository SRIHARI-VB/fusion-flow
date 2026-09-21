import { useNavigate } from "react-router-dom";
import { AxiosError } from "axios";
import { Mail } from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@fusion-flow/ui";
import { useConnectConnector } from "../../hooks";

/**
 * Gmail's "connect" step: `auth_mode="oauth"`, so unlike Razorpay/WhatsApp
 * there is no form to fill in - `config_schema` is empty on the backend
 * (`gmail/adapter.py`'s `CONFIG_SCHEMA`). Clicking the button below calls
 * `POST /connectors/gmail/connect` with an empty `params` object; the
 * backend responds with a `redirect_url` pointing at Google's consent
 * screen, and this step's only job is to send the browser there.
 *
 * `Mail` (lucide-react) is a placeholder icon until real per-provider
 * branding/logos land separately - not this task's concern.
 */
export function GmailConnectStep() {
  const navigate = useNavigate();
  const { mutate, isPending, error } = useConnectConnector();

  function handleConnect() {
    mutate(
      { typeKey: "gmail", payload: { params: {} } },
      {
        onSuccess: (response) => {
          if (response.redirect_url) {
            window.location.href = response.redirect_url;
          } else {
            navigate(`/connectors/${response.instance.id}?connected=1`);
          }
        },
      },
    );
  }

  const mutationError = error as AxiosError<{ detail?: string }> | null;

  return (
    <Card className="mx-auto max-w-lg">
      <CardHeader className="items-center text-center">
        <div className="mb-2 flex h-14 w-14 items-center justify-center rounded-full bg-accent-soft text-accent">
          <Mail className="h-7 w-7" />
        </div>
        <CardTitle>Connect Gmail</CardTitle>
        <CardDescription>
          Connect Gmail to send emails and read recent messages from your workflows. You'll be sent to
          Google to sign in and grant access - your credentials are never seen or stored by this app.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-4">
          {mutationError && (
            <p className="text-sm text-destructive">
              {mutationError.response?.data?.detail ?? "Could not connect this Gmail account."}
            </p>
          )}

          <Button type="button" disabled={isPending} className="mt-2" onClick={handleConnect}>
            <Mail className="h-4 w-4" />
            {isPending ? "Connecting…" : "Connect with Google"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
