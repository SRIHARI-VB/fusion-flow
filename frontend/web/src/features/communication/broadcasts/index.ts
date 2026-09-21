/**
 * Public surface of the broadcast-campaigns feature - import pages from
 * here to mount them in `App.tsx` (list at `/communication/broadcasts`,
 * create at `/communication/broadcasts/new`). Nothing in `App.tsx` is
 * edited by this feature - that file is outside this feature's ownership
 * boundary for this wave.
 */

export { BroadcastCampaignsListPage } from "./pages/BroadcastCampaignsListPage";
export { BroadcastCampaignWizardPage } from "./pages/BroadcastCampaignWizardPage";

export * from "./types";
export * from "./hooks";
