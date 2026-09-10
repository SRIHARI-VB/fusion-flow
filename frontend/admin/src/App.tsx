import { Navigate, Route, Routes } from "react-router-dom";
import { AdminLayout } from "./components/AdminLayout";
import { RequireAdmin } from "./components/RequireAdmin";
import { LoginPage } from "./pages/Login";
import { TenantsPage } from "./features/tenants/TenantsPage";
import { TenantDetailPage } from "./features/tenants/TenantDetailPage";
import { AuditLogPage } from "./features/audit-log/AuditLogPage";
import { FeatureFlagsPage } from "./features/feature-flags/FeatureFlagsPage";
import { TemplatesPage } from "./features/templates/TemplatesPage";
import { WorkflowNodeTemplatesPage } from "./features/workflow-node-templates/WorkflowNodeTemplatesPage";
import { PlansPage } from "./features/plans/PlansPage";
import { ConnectorRequestsPage } from "./features/connector-requests/ConnectorRequestsPage";
import { BillingPage } from "./features/billing/BillingPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route
        element={
          <RequireAdmin>
            <AdminLayout />
          </RequireAdmin>
        }
      >
        <Route path="/tenants" element={<TenantsPage />} />
        <Route path="/tenants/:id" element={<TenantDetailPage />} />
        <Route path="/audit-log" element={<AuditLogPage />} />
        <Route path="/feature-flags" element={<FeatureFlagsPage />} />
        <Route path="/templates" element={<TemplatesPage />} />
        <Route path="/workflow-node-templates" element={<WorkflowNodeTemplatesPage />} />
        <Route path="/plans" element={<PlansPage />} />
        <Route path="/connector-requests" element={<ConnectorRequestsPage />} />
        <Route path="/billing" element={<BillingPage />} />
        <Route path="/" element={<Navigate to="/tenants" replace />} />
      </Route>

      <Route path="*" element={<Navigate to="/tenants" replace />} />
    </Routes>
  );
}
