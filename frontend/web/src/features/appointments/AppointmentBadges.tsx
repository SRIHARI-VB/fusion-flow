import { Badge } from "@fusion-flow/ui";
import { MapPin, Video } from "lucide-react";
import type { AppointmentMode } from "./types";

/** Online/offline indicator with a small icon, per the appointment's `appointment_mode`. */
export function ModeBadge({ mode }: { mode: AppointmentMode | null }) {
  if (!mode) return null;
  if (mode === "online") {
    return (
      <Badge variant="secondary" className="gap-1">
        <Video className="h-3 w-3" />
        Online
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="gap-1">
      <MapPin className="h-3 w-3" />
      In-person
    </Badge>
  );
}

const STATUS_VARIANT: Record<string, "success" | "destructive" | "secondary" | "default"> = {
  confirmed: "success",
  completed: "success",
  cancelled: "destructive",
  canceled: "destructive",
  pending: "secondary",
};

/** Color-coded status pill; falls back to the default (accent) look for statuses we don't specifically recognize. */
export function StatusBadge({ status }: { status: string | null }) {
  if (!status) return null;
  const variant = STATUS_VARIANT[status.toLowerCase()] ?? "default";
  return (
    <Badge variant={variant} className="capitalize">
      {status}
    </Badge>
  );
}
