import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./components/layout/AppLayout";
import { RequireAuth } from "./components/auth/RequireAuth";
import { PlaceholderPage } from "./pages/Placeholder";
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
import { OrdersListPage, OrderDetailPage } from "./features/orders";
import { PaymentsPage } from "./features/payments";
import { TicketsListPage, TicketDetailPage } from "./features/tickets";
import { KbPage } from "./features/kb";
import {
  ConnectorsGridPage,
  ConnectorDetailPage,
  WhatsAppConnectPage,
  RazorpayConnectPage,
} from "./features/connectors";
import { WorkflowsListPage, WorkflowEditorPage, WorkflowRunsPage } from "./features/workflows";

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

        <Route path="/products" element={<ProductsPage />} />
        <Route path="/services" element={<ServicesPage />} />
        <Route path="/coupons" element={<CouponsPage />} />
        <Route path="/offers" element={<OffersPage />} />

        <Route path="/customers" element={<CustomersPage />} />
        <Route path="/orders" element={<OrdersListPage />} />
        <Route path="/orders/:id" element={<OrderDetailPage />} />
        <Route path="/payments" element={<PaymentsPage />} />
        <Route path="/tickets" element={<TicketsListPage />} />
        <Route path="/tickets/:id" element={<TicketDetailPage />} />
        <Route path="/kb" element={<KbPage />} />

        <Route path="/connectors" element={<ConnectorsGridPage />} />
        <Route path="/connectors/whatsapp/connect" element={<WhatsAppConnectPage />} />
        <Route path="/connectors/razorpay/connect" element={<RazorpayConnectPage />} />
        <Route path="/connectors/:instanceId" element={<ConnectorDetailPage />} />

        <Route path="/workflows" element={<WorkflowsListPage />} />
        <Route path="/workflows/:id/edit" element={<WorkflowEditorPage />} />
        <Route path="/workflows/:id/runs" element={<WorkflowRunsPage />} />

        <Route path="/support-agent" element={<PlaceholderPage title="Support Agent" description="Hidden behind the support_agent_enabled feature flag until phase 2." />} />

        <Route path="/settings/custom-fields" element={<CustomFieldsSettingsPage />} />
        <Route path="/settings" element={<SettingsPage />} />

        <Route path="/" element={<Navigate to="/dashboard" replace />} />
      </Route>

      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
