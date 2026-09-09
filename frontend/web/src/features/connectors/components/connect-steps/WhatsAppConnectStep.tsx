import { useNavigate, useSearchParams } from "react-router-dom";
import { MessageCircle } from "lucide-react";
import { AxiosError } from "axios";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@fusion-flow/ui";
import { useConnectConnector } from "../../hooks";

/**
 * WhatsApp's "connect" step: a single embedded-signup launch button.
 *
 * Real Meta Embedded Signup runs a JS SDK popup client-side and posts a
 * short-lived `code` back to us; that SDK integration is out of scope here
 * (per the task brief, "doesn't need real Meta SDK JS") - this button
 * instead calls the backend's connect endpoint directly and follows
 * whatever it returns:
 *  - a real Meta app configured -> backend returns `redirect_url` (Meta's
 *    OAuth dialog) and we do a full-page redirect there; Meta eventually
 *    bounces the browser back to the backend's OAuth callback route, which
 *    itself redirects here (`/connectors/whatsapp/connect?error=...`) or to
 *    the instance detail page on success.
 *  - no Meta app configured (this dev environment) -> the backend's stub
 *    path completes the "connection" synchronously and returns the new
 *    instance with no redirect - we just navigate to its detail page.
 */
export function WhatsAppConnectStep() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const oauthError = searchParams.get("error");
  const { mutate, isPending, error } = useConnectConnector();

  function handleLaunch() {
    mutate(
      { typeKey: "whatsapp", payload: { params: {} } },
      {
        onSuccess: (response) => {
          if (response.redirect_url) {
            window.location.href = response.redirect_url;
            return;
          }
          navigate(`/connectors/${response.instance.id}?connected=1`);
        },
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
          Launch Meta's Embedded Signup to link a WhatsApp Business Account to fusion-flow. You'll be
          redirected to Meta to grant access, then brought back here automatically.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col items-center gap-4">
        {(oauthError || mutationError) && (
          <p className="text-center text-sm text-destructive">
            {oauthError ?? mutationError?.response?.data?.detail ?? "Could not start the WhatsApp connection."}
          </p>
        )}
        <Button size="lg" onClick={handleLaunch} disabled={isPending}>
          <MessageCircle className="h-4 w-4" />
          {isPending ? "Connecting…" : "Connect with WhatsApp"}
        </Button>
        <p className="text-center text-xs text-muted-foreground">
          You'll need admin access to the Meta Business Manager that owns the WhatsApp number.
        </p>
      </CardContent>
    </Card>
  );
}
