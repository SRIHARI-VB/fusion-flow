import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { WhatsAppConnectStep } from "../components/connect-steps/WhatsAppConnectStep";

/** `/connectors/whatsapp/connect` */
export function WhatsAppConnectPage() {
  return (
    <div className="flex flex-col gap-6">
      <Link
        to="/connectors"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to connectors
      </Link>
      <WhatsAppConnectStep />
    </div>
  );
}
