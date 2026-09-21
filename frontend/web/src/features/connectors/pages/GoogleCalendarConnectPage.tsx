import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { GoogleCalendarConnectStep } from "../components/connect-steps/GoogleCalendarConnectStep";

/** `/connectors/google_calendar/connect` */
export function GoogleCalendarConnectPage() {
  return (
    <div className="flex flex-col gap-6">
      <Link
        to="/connectors"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to connectors
      </Link>
      <GoogleCalendarConnectStep />
    </div>
  );
}
