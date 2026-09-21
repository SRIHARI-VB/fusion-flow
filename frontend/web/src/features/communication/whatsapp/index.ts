/**
 * Public surface of the WhatsApp appointment-booking automation feature -
 * import pages from here to mount them in `App.tsx` (routes:
 * `/communication/whatsapp/automations`,
 * `/communication/whatsapp/automations/new`,
 * `/communication/whatsapp/automations/:id/edit`). `App.tsx` is not edited
 * by this feature - that file is outside this feature's ownership
 * boundary for this wave.
 */

export { WhatsAppAutomationsListPage } from "./pages/WhatsAppAutomationsListPage";
export { WhatsAppAutomationWizardPage } from "./pages/WhatsAppAutomationWizardPage";

export * from "./api";
export * from "./hooks";
