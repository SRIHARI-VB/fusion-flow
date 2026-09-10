import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./components/layout/AppLayout";
import { RequireAuth } from "./components/auth/RequireAuth";
import { RequireModule } from "./components/auth/RequireModule";
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

        <Route path="/products" element={<RequireModule moduleKey="products"><ProductsPage /></RequireModule>} />
        <Route path="/services" element={<RequireModule moduleKey="services"><ServicesPage /></RequireModule>} />
        <Route path="/coupons" element={<RequireModule moduleKey="coupons"><CouponsPage /></RequireModule>} />
        <Route path="/offers" element={<RequireModule moduleKey="offers"><OffersPage /></RequireModule>} />

        <Route path="/customers" element={<RequireModule moduleKey="customers"><CustomersPage /></RequireModule>} />
        <Route path="/orders" element={<RequireModule moduleKey="orders"><OrdersListPage /></RequireModule>} />
        <Route path="/orders/:id" element={<RequireModule moduleKey="orders"><OrderDetailPage /></RequireModule>} />
        <Route path="/payments" element={<RequireModule moduleKey="payments"><PaymentsPage /></RequireModule>} />
        <Route path="/tickets" element={<RequireModule moduleKey="tickets"><TicketsListPage /></RequireModule>} />
        <Route path="/tickets/:id" element={<RequireModule moduleKey="tickets"><TicketDetailPage /></RequireModule>} />
        <Route path="/kb" element={<RequireModule moduleKey="kb"><KbPage /></RequireModule>} />

        <Route path="/connectors" element={<ConnectorsGridPage />} />
        <Route path="/connectors/whatsapp/connect" element={<WhatsAppConnectPage />} />
        <Route path="/connectors/razorpay/connect" element={<RazorpayConnectPage />} />
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

        <Route
          path="/support-agent"
          element={
            <RequireModule moduleKey="support_agent">
              <PlaceholderPage title="Support Agent" description="Coming in a later phase." />
            </RequireModule>
          }
        />

        <Route
          path="/settings/custom-fields"
          element={<RequireModule moduleKey="custom_fields"><CustomFieldsSettingsPage /></RequireModule>}
        />
        <Route path="/settings" element={<SettingsPage />} />

        <Route path="/" element={<Navigate to="/dashboard" replace />} />
      </Route>

      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
