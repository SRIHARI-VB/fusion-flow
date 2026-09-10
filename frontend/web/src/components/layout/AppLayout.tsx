import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

export function AppLayout() {
  // `h-screen overflow-hidden` (not `min-h-screen`) is required, not
  // cosmetic: `min-h-screen` only sets a floor, so once a page's content
  // grew taller than the viewport this container grew with it, dragging
  // the sidebar down and making the *whole page* scroll instead of just
  // `<main>`. Pinning this to exactly the viewport height means only
  // `<main>`'s own `overflow-y-auto` can ever scroll; the sidebar and
  // topbar stay fixed.
  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar />
      <div className="flex h-screen flex-1 flex-col overflow-hidden">
        <Topbar />
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
