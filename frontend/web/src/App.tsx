import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./components/layout/AppLayout";
import { RequireAuth } from "./components/auth/RequireAuth";
import { RequireModule } from "./components/auth/RequireModule";
import { RequireStepUp } from "./components/auth/RequireStepUp";
import { LoginPage } from "./pages/Login";
import { SignupPage } from "./pages/Signup";
import { ApplicationSubmittedPage } from "./pages/ApplicationSubmitted";
import { SelectBusinessPage } from "./pages/SelectBusiness";
import { DashboardPage } from "./pages/Dashboard";
import { OnboardingPage } from "./features/onboarding";
import { CustomFieldsSettingsPage } from "./features/custom-fields";
import { SettingsPage } from "./features/settings";
import { ProductsPage, ServicesPage, CouponsPage, OffersPage } from "./features/catalog";
import { CustomersPage } from "./features/customers";
import { AppointmentRecordsPage } from "./features/appointments";
import { OrdersListPage, OrderDetailPage } from "./features/orders";
import { PaymentsPage } from "./features/payments";
import { TicketsListPage, TicketDetailPage } from "./features/tickets";
import { ClinicQueuePage, HistoryPage as ClinicQueueHistoryPage } from "./features/clinic-queue";
import { KbPage } from "./features/kb";
import {
  ConnectorsGridPage,
  ConnectorDetailPage,
  WhatsAppConnectPage,
  RazorpayConnectPage,
  CloudflareR2ConnectPage,
  InstagramConnectPage,
  GoogleCalendarConnectPage,
  GmailConnectPage,
  GoogleMeetConnectPage,
  GoogleSheetsConnectPage,
} from "./features/connectors";
import { WorkflowsListPage, WorkflowEditorPage, WorkflowRunsPage } from "./features/workflows";
import { WhatsAppAutomationsListPage, WhatsAppAutomationWizardPage } from "./features/communication/whatsapp";
import {
  InstagramAutomationsListPage,
  InstagramAutomationWizardPage,
  InstagramDmAutomationWizardPage,
  InstagramMentionAutomationWizardPage,
  InstagramCommentModerationWizardPage,
  InstagramStoryReplyAutomationWizardPage,
  InstagramButtonMenuAutomationWizardPage,
  InstagramReferralAutomationWizardPage,
  InstagramReactionAutomationWizardPage,
  InstagramHandoffAutomationWizardPage,
  InstagramIceBreakersSettingsPage,
} from "./features/communication/instagram";
import { InboxPage } from "./features/communication/inbox";
import { QuickRepliesPage } from "./features/communication/quick-replies";
import { MediaLibraryPage } from "./features/communication/media-library";
import { BroadcastCampaignsListPage, BroadcastCampaignWizardPage } from "./features/communication/broadcasts";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route path="/application-submitted" element={<ApplicationSubmittedPage />} />
      <Route path="/select-business" element={<SelectBusinessPage />} />

      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route path="/dashboard" element={<DashboardPage />} />

        <Route path="/onboarding" element={<OnboardingPage />} />

        <Route path="/products" element={<RequireModule moduleKey="products"><ProductsPage /></RequireModule>} />
        <Route path="/services" element={<RequireModule moduleKey="services"><ServicesPage /></RequireModule>} />
        <Route path="/coupons" element={<RequireModule moduleKey="coupons"><CouponsPage /></RequireModule>} />
        <Route path="/offers" element={<RequireModule moduleKey="offers"><OffersPage /></RequireModule>} />

        <Route path="/customers" element={<RequireModule moduleKey="customers"><CustomersPage /></RequireModule>} />
        {/* Appointments itself is a real page with its own "appointments"
            moduleKey, even though the underlying business_objects API it
            calls has no module gate of its own (it's tenant-owned metadata,
            not a platform feature toggle - see business_objects/router.py's
            module docstring). */}
        <Route
          path="/appointments"
          element={<RequireModule moduleKey="appointments"><AppointmentRecordsPage /></RequireModule>}
        />
        <Route path="/orders" element={<RequireModule moduleKey="orders"><OrdersListPage /></RequireModule>} />
        <Route path="/orders/:id" element={<RequireModule moduleKey="orders"><OrderDetailPage /></RequireModule>} />
        <Route path="/payments" element={<RequireModule moduleKey="payments"><PaymentsPage /></RequireModule>} />
        <Route path="/tickets" element={<RequireModule moduleKey="tickets"><TicketsListPage /></RequireModule>} />
        <Route path="/tickets/:id" element={<RequireModule moduleKey="tickets"><TicketDetailPage /></RequireModule>} />
        <Route path="/kb" element={<RequireModule moduleKey="kb"><KbPage /></RequireModule>} />

        <Route
          path="/clinic-queue"
          element={
            <RequireModule moduleKey="clinic_queue">
              <RequireStepUp
                when={(b) => !!b?.is_doctor}
                reason="The Patient Flow board includes consultation notes only doctors can see - please re-enter your password to continue."
              >
                <ClinicQueuePage />
              </RequireStepUp>
            </RequireModule>
          }
        />
        <Route
          path="/clinic-queue/history"
          element={
            <RequireModule moduleKey="clinic_queue">
              <RequireStepUp
                when={(b) => !!b?.is_doctor}
                reason="The Patient Flow board includes consultation notes only doctors can see - please re-enter your password to continue."
              >
                <ClinicQueueHistoryPage />
              </RequireStepUp>
            </RequireModule>
          }
        />

        <Route path="/connectors" element={<ConnectorsGridPage />} />
        <Route path="/connectors/whatsapp/connect" element={<WhatsAppConnectPage />} />
        <Route path="/connectors/razorpay/connect" element={<RazorpayConnectPage />} />
        <Route path="/connectors/cloudflare_r2/connect" element={<CloudflareR2ConnectPage />} />
        <Route path="/connectors/instagram/connect" element={<InstagramConnectPage />} />
        <Route path="/connectors/google_calendar/connect" element={<GoogleCalendarConnectPage />} />
        <Route path="/connectors/gmail/connect" element={<GmailConnectPage />} />
        <Route path="/connectors/google_meet/connect" element={<GoogleMeetConnectPage />} />
        <Route path="/connectors/google_sheets/connect" element={<GoogleSheetsConnectPage />} />
        <Route path="/connectors/:instanceId" element={<ConnectorDetailPage />} />

        <Route path="/workflows" element={<RequireModule moduleKey="workflows"><WorkflowsListPage /></RequireModule>} />
        <Route
          path="/workflows/:id/edit"
          element={<RequireModule moduleKey="workflows"><WorkflowEditorPage /></RequireModule>}
        />
        <Route
          path="/workflows/:id/runs"
          element={<RequireModule moduleKey="workflows"><WorkflowRunsPage /></RequireModule>}
        />

        {/* Communication */}
        <Route
          path="/communication/whatsapp/automations"
          element={<RequireModule moduleKey="whatsapp"><WhatsAppAutomationsListPage /></RequireModule>}
        />
        <Route
          path="/communication/whatsapp/automations/new"
          element={<RequireModule moduleKey="whatsapp"><WhatsAppAutomationWizardPage /></RequireModule>}
        />
        <Route
          path="/communication/whatsapp/automations/:id/edit"
          element={<RequireModule moduleKey="whatsapp"><WhatsAppAutomationWizardPage /></RequireModule>}
        />
        <Route
          path="/communication/instagram/automations"
          element={<RequireModule moduleKey="instagram"><InstagramAutomationsListPage /></RequireModule>}
        />
        <Route
          path="/communication/instagram/automations/new"
          element={<RequireModule moduleKey="instagram"><InstagramAutomationWizardPage /></RequireModule>}
        />
        <Route
          path="/communication/instagram/automations/:id/edit"
          element={<RequireModule moduleKey="instagram"><InstagramAutomationWizardPage /></RequireModule>}
        />
        <Route
          path="/communication/instagram/dm-automations/new"
          element={<RequireModule moduleKey="instagram"><InstagramDmAutomationWizardPage /></RequireModule>}
        />
        <Route
          path="/communication/instagram/dm-automations/:id/edit"
          element={<RequireModule moduleKey="instagram"><InstagramDmAutomationWizardPage /></RequireModule>}
        />
        <Route
          path="/communication/instagram/mention-automations/new"
          element={<RequireModule moduleKey="instagram"><InstagramMentionAutomationWizardPage /></RequireModule>}
        />
        <Route
          path="/communication/instagram/mention-automations/:id/edit"
          element={<RequireModule moduleKey="instagram"><InstagramMentionAutomationWizardPage /></RequireModule>}
        />
        <Route
          path="/communication/instagram/moderation-automations/new"
          element={<RequireModule moduleKey="instagram"><InstagramCommentModerationWizardPage /></RequireModule>}
        />
        <Route
          path="/communication/instagram/moderation-automations/:id/edit"
          element={<RequireModule moduleKey="instagram"><InstagramCommentModerationWizardPage /></RequireModule>}
        />
        <Route
          path="/communication/instagram/story-reply-automations/new"
          element={<RequireModule moduleKey="instagram"><InstagramStoryReplyAutomationWizardPage /></RequireModule>}
        />
        <Route
          path="/communication/instagram/story-reply-automations/:id/edit"
          element={<RequireModule moduleKey="instagram"><InstagramStoryReplyAutomationWizardPage /></RequireModule>}
        />
        <Route
          path="/communication/instagram/button-menu-automations/new"
          element={<RequireModule moduleKey="instagram"><InstagramButtonMenuAutomationWizardPage /></RequireModule>}
        />
        <Route
          path="/communication/instagram/button-menu-automations/:id/edit"
          element={<RequireModule moduleKey="instagram"><InstagramButtonMenuAutomationWizardPage /></RequireModule>}
        />
        <Route
          path="/communication/instagram/referral-automations/new"
          element={<RequireModule moduleKey="instagram"><InstagramReferralAutomationWizardPage /></RequireModule>}
        />
        <Route
          path="/communication/instagram/referral-automations/:id/edit"
          element={<RequireModule moduleKey="instagram"><InstagramReferralAutomationWizardPage /></RequireModule>}
        />
        <Route
          path="/communication/instagram/reaction-automations/new"
          element={<RequireModule moduleKey="instagram"><InstagramReactionAutomationWizardPage /></RequireModule>}
        />
        <Route
          path="/communication/instagram/reaction-automations/:id/edit"
          element={<RequireModule moduleKey="instagram"><InstagramReactionAutomationWizardPage /></RequireModule>}
        />
        <Route
          path="/communication/instagram/handoff-automations/new"
          element={<RequireModule moduleKey="instagram"><InstagramHandoffAutomationWizardPage /></RequireModule>}
        />
        <Route
          path="/communication/instagram/handoff-automations/:id/edit"
          element={<RequireModule moduleKey="instagram"><InstagramHandoffAutomationWizardPage /></RequireModule>}
        />
        <Route
          path="/communication/instagram/ice-breakers"
          element={<RequireModule moduleKey="instagram"><InstagramIceBreakersSettingsPage /></RequireModule>}
        />
        <Route path="/communication/inbox" element={<InboxPage />} />
        <Route path="/communication/quick-replies" element={<QuickRepliesPage />} />
        <Route path="/communication/media-library" element={<MediaLibraryPage />} />
        <Route path="/communication/broadcasts" element={<BroadcastCampaignsListPage />} />
        <Route path="/communication/broadcasts/new" element={<BroadcastCampaignWizardPage />} />

        <Route
          path="/settings/custom-fields"
          element={<RequireModule moduleKey="custom_fields"><CustomFieldsSettingsPage /></RequireModule>}
        />
        <Route
          path="/settings"
          element={
            <RequireStepUp
              when={(b) => b?.role === "owner"}
              reason="You're signed in as this business's owner - please re-enter your password to open Settings."
            >
              <SettingsPage />
            </RequireStepUp>
          }
        />

        <Route path="/" element={<Navigate to="/dashboard" replace />} />
      </Route>

      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
