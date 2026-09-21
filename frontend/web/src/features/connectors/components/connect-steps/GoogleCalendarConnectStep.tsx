import { useNavigate } from "react-router-dom";
import { AxiosError } from "axios";
import { Calendar } from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@fusion-flow/ui";
import { useConnectConnector } from "../../hooks";

/**
 * Google Calendar's "connect" step: `auth_mode="oauth"`, so there is no
 * form to fill in (`config_schema` is an empty object - see
 * `google_calendar/adapter.py`) - the tenant clicks one button and is
 * redirected to Google's own consent screen. `Calendar` (lucide-react) is
 * a placeholder icon until a real per-provider logo set lands separately.
 */
export function GoogleCalendarConnectStep() {
  const navigate = useNavigate();
  const { mutate, isPending, error } = useConnectConnector();

  function handleConnect() {
    mutate(
      { typeKey: "google_calendar", payload: { params: {} } },
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
          <Calendar className="h-7 w-7" />
        </div>
        <CardTitle>Connect Google Calendar</CardTitle>
        <CardDescription>
          Connect your Google Calendar to create, list, and update events from your workflows. You&apos;ll be
          redirected to Google to grant access, then brought back here.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-4">
          {mutationError && (
            <p className="text-sm text-destructive">
              {mutationError.response?.data?.detail ?? "Could not connect this Google Calendar account."}
            </p>
          )}

          <Button type="button" disabled={isPending} className="mt-2" onClick={handleConnect}>
            <Calendar className="h-4 w-4" />
            {isPending ? "Connecting…" : "Connect with Google"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
