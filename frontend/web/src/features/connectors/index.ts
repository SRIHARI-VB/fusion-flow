/**
 * Public surface of the connectors feature - import pages from here to
 * mount them in `App.tsx` (see this task's final report for the exact
 * route paths/props). Nothing in `App.tsx` is edited by this feature -
 * that file is outside this feature's ownership boundary for this wave.
 */

export { ConnectorsGridPage } from "./pages/ConnectorsGridPage";
export { ConnectorDetailPage } from "./pages/ConnectorDetailPage";
export { WhatsAppConnectPage } from "./pages/WhatsAppConnectPage";
export { RazorpayConnectPage } from "./pages/RazorpayConnectPage";
export { CloudflareR2ConnectPage } from "./pages/CloudflareR2ConnectPage";
export { InstagramConnectPage } from "./pages/InstagramConnectPage";
export { GoogleCalendarConnectPage } from "./pages/GoogleCalendarConnectPage";
export { GmailConnectPage } from "./pages/GmailConnectPage";
export { GoogleMeetConnectPage } from "./pages/GoogleMeetConnectPage";
export { GoogleSheetsConnectPage } from "./pages/GoogleSheetsConnectPage";

export { ConnectorCard } from "./components/ConnectorCard";
export { ConnectorEventsTable } from "./components/ConnectorEventsTable";
export { ConfirmDialog } from "./components/ConfirmDialog";
export { WhatsAppConnectStep } from "./components/connect-steps/WhatsAppConnectStep";
export { RazorpayConnectStep } from "./components/connect-steps/RazorpayConnectStep";
export { CloudflareR2ConnectStep } from "./components/connect-steps/CloudflareR2ConnectStep";
export { InstagramConnectStep } from "./components/connect-steps/InstagramConnectStep";
export { GoogleCalendarConnectStep } from "./components/connect-steps/GoogleCalendarConnectStep";
export { GmailConnectStep } from "./components/connect-steps/GmailConnectStep";
export { GoogleMeetConnectStep } from "./components/connect-steps/GoogleMeetConnectStep";
export { GoogleSheetsConnectStep } from "./components/connect-steps/GoogleSheetsConnectStep";

export { CONNECTOR_LOGO } from "./connector-logos";

export * from "./types";
export * from "./hooks";
