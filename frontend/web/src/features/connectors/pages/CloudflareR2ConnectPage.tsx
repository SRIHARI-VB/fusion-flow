import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { CloudflareR2ConnectStep } from "../components/connect-steps/CloudflareR2ConnectStep";

/** `/connectors/cloudflare_r2/connect` */
export function CloudflareR2ConnectPage() {
  return (
    <div className="flex flex-col gap-6">
      <Link
        to="/connectors"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to connectors
      </Link>
      <CloudflareR2ConnectStep />
    </div>
  );
}
