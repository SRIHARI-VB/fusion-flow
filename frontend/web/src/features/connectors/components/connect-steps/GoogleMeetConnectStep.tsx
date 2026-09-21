import { useNavigate } from "react-router-dom";
import { AxiosError } from "axios";
import { Video } from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@fusion-flow/ui";
import { useConnectConnector } from "../../hooks";

/**
 * Google Meet's "connect" step: `auth_mode="oauth"`, so unlike Razorpay's
 * pasted-key-pair form there is nothing for the tenant to fill in - the
 * backend's `config_schema` for this connector is an empty object. Clicking
 * "Connect with Google" calls `POST /connectors/google_meet/connect` with
 * empty `params`, which starts a `ConnectorOAuthState` row and returns a
 * Google consent-screen `redirect_url`; this component's only job is to
 * kick that off and then hand the browser to Google. The actual token
 * exchange happens later, out of band, when Google redirects back to the
 * generic `GET /connectors/oauth/callback/google_meet` route.
 *
 * `Video` (lucide-react) is a placeholder icon until per-provider branded
 * logos land separately - not this task's concern.
 */
export function GoogleMeetConnectStep() {
  const navigate = useNavigate();
  const { mutate, isPending, error } = useConnectConnector();

  function handleConnect() {
    mutate(
      { typeKey: "google_meet", payload: { params: {} } },
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
          <Video className="h-7 w-7" />
        </div>
        <CardTitle>Connect Google Meet</CardTitle>
        <CardDescription>
          Connect Google Meet to create meeting links from your workflows. You&apos;ll be redirected to
          Google to grant access, then brought back here.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-4">
          {mutationError && (
            <p className="text-sm text-destructive">
              {mutationError.response?.data?.detail ?? "Could not connect Google Meet."}
            </p>
          )}

          <Button type="button" disabled={isPending} className="mt-2" onClick={handleConnect}>
            <Video className="h-4 w-4" />
            {isPending ? "Connecting…" : "Connect with Google"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
