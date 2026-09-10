import type { ComponentType } from "react";
import type { ConnectorInstance } from "../types";
import { WhatsAppSettingsPanel } from "./WhatsAppSettingsPanel";

/**
 * `connector_type_key -> settings panel component`, rendered by
 * `ConnectorDetailPage.tsx`'s new "Settings" tab. This is the reusable
 * half of Part F: a connector with nothing registered here simply gets
 * the tab's plain fallback message - existing connectors (Razorpay) are
 * unaffected by adding a new entry for WhatsApp.
 *
 * To give a future connector its own settings UI: build a panel
 * component (props: `{instance: ConnectorInstance}`) and add one line
 * here - no `ConnectorDetailPage.tsx` changes needed.
 */
export const CONNECTOR_SETTINGS: Record<string, ComponentType<{ instance: ConnectorInstance }>> = {
  whatsapp: WhatsAppSettingsPanel,
};
