import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./components/layout/AppLayout";
import { RequireAuth } from "./components/auth/RequireAuth";
import { PlaceholderPage } from "./pages/Placeholder";
import { LoginPage } from "./pages/Login";
import { SignupPage } from "./pages/Signup";
import { SelectBusinessPage } from "./pages/SelectBusiness";
import { DashboardPage } from "./pages/Dashboard";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route path="/select-business" element={<SelectBusinessPage />} />

      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route path="/dashboard" element={<DashboardPage />} />

        <Route path="/onboarding" element={<PlaceholderPage title="Onboarding" description="Business info, vertical selection, template application, and optional invite/connect steps." />} />

        <Route path="/products" element={<PlaceholderPage title="Products" />} />
        <Route path="/services" element={<PlaceholderPage title="Services" />} />
        <Route path="/coupons" element={<PlaceholderPage title="Coupons" />} />
        <Route path="/offers" element={<PlaceholderPage title="Offers" />} />

        <Route path="/customers" element={<PlaceholderPage title="Customers" />} />
        <Route path="/orders" element={<PlaceholderPage title="Orders" />} />
        <Route path="/payments" element={<PlaceholderPage title="Payments" />} />
        <Route path="/tickets" element={<PlaceholderPage title="Tickets" />} />
        <Route path="/kb" element={<PlaceholderPage title="Knowledge Base" />} />

        <Route path="/connectors" element={<PlaceholderPage title="Connectors" description="Generic connector grid — WhatsApp, Razorpay, and future providers." />} />
        <Route path="/connectors/:instanceId" element={<PlaceholderPage title="Connector Detail" />} />

        <Route path="/workflows" element={<PlaceholderPage title="Workflows" />} />
        <Route path="/workflows/:id/edit" element={<PlaceholderPage title="Workflow Editor" description="React Flow canvas + config drawer + validation panel + publish." />} />
        <Route path="/workflows/:id/runs" element={<PlaceholderPage title="Workflow Runs" />} />

        <Route path="/support-agent" element={<PlaceholderPage title="Support Agent" description="Hidden behind the support_agent_enabled feature flag until phase 2." />} />

        <Route path="/settings" element={<PlaceholderPage title="Settings" description="Profile, members, messaging kill switch, danger zone." />} />

        <Route path="/" element={<Navigate to="/dashboard" replace />} />
      </Route>

      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
