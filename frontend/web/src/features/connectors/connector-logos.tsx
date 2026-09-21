import type { ComponentType } from "react";
import type { IconBaseProps } from "react-icons";
import {
  SiCloudflare,
  SiGmail,
  SiGooglecalendar,
  SiGooglemeet,
  SiGooglesheets,
  SiInstagram,
  SiRazorpay,
  SiWhatsapp,
} from "react-icons/si";

/**
 * Real per-connector brand marks, keyed by `connector_types.key` - takes
 * priority over `CONNECTOR_CATEGORY_ICON` (a generic lucide icon shared by
 * every connector in a category) wherever a connector card/detail view
 * renders an icon. See `ConnectorCard.tsx`.
 *
 * Sourced from Simple Icons (via `react-icons/si`) rather than hand-drawn -
 * these are the actual maintained, officially-shaped brand marks, not an
 * approximation. Each is single-color by design (Simple Icons' own
 * convention); `BRAND_COLOR` supplies each provider's own brand hex so the
 * mark isn't rendered in whatever the surrounding text color happens to be.
 * `lucide-react` (this app's generic icon set everywhere else) has no
 * brand-logo coverage, so this is scoped to connector logos only rather
 * than swapping the whole app onto a second icon library.
 */

export const CONNECTOR_LOGO: Record<string, ComponentType<IconBaseProps>> = {
  whatsapp: SiWhatsapp,
  razorpay: SiRazorpay,
  cloudflare_r2: SiCloudflare,
  instagram: SiInstagram,
  google_calendar: SiGooglecalendar,
  gmail: SiGmail,
  google_meet: SiGooglemeet,
  google_sheets: SiGooglesheets,
};

export const CONNECTOR_LOGO_COLOR: Record<string, string> = {
  whatsapp: "#25D366",
  razorpay: "#0C2451",
  cloudflare_r2: "#F38020",
  instagram: "#E4405F",
  google_calendar: "#4285F4",
  gmail: "#EA4335",
  google_meet: "#00897B",
  google_sheets: "#0F9D58",
};
