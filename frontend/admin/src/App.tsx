import { Navigate, Route, Routes } from "react-router-dom";
import { AdminLayout } from "./components/AdminLayout";
import { RequireAdmin } from "./components/RequireAdmin";
import { LoginPage } from "./pages/Login";
import { TenantsPage } from "./pages/Tenants";

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
        <Route path="/" element={<Navigate to="/tenants" replace />} />
      </Route>

      <Route path="*" element={<Navigate to="/tenants" replace />} />
    </Routes>
  );
}
