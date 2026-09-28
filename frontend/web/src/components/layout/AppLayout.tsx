import { Outlet } from "react-router-dom";
import { useLayoutStore } from "../../lib/layout-store";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { PageTitleProvider } from "./page-title";

export function AppLayout() {
  // `h-screen overflow-hidden` (not `min-h-screen`) is required, not
  // cosmetic: `min-h-screen` only sets a floor, so once a page's content
  // grew taller than the viewport this container grew with it, dragging
  // the sidebar down and making the *whole page* scroll instead of just
  // `<main>`. Pinning this to exactly the viewport height means only
  // `<main>`'s own `overflow-y-auto` can ever scroll; the sidebar and
  // topbar stay fixed.
  //
  // `fullView` (set by `WorkflowEditorPage.tsx`, reset on its unmount) hides
  // both `Sidebar`/`Topbar` and drops `<main>`'s padding/scroll so the
  // workflow canvas gets the entire viewport - a per-editing-session
  // toggle, not a durable layout preference like `sidebarCollapsed`.
  //
  // Critical: this must NEVER change the *shape* of the tree surrounding
  // `<Outlet />` (e.g. by `return`-ing two differently-structured trees
  // depending on `fullView`) - React can only reconcile matching element
  // types at matching positions in place; a structurally different tree
  // forces it to unmount and remount everything `<Outlet />` renders. Since
  // `WorkflowEditorPage` resets `fullView` to `false` in its own unmount
  // cleanup, that remount would immediately flip `fullView` back to
  // `false`, which re-renders *this* component back to the non-full-view
  // shape, remounting `<Outlet />` a second time - an infinite toggle loop
  // that looked like the page "blinking" instead of expanding. Keeping the
  // exact same element tree in both modes (toggling only visibility/
  // classes) avoids ever unmounting the routed page at all.
  const fullView = useLayoutStore((s) => s.fullView);

  return (
    <PageTitleProvider>
      <div className="flex h-screen overflow-hidden bg-background">
        {!fullView && <Sidebar />}
        <div className="flex h-screen flex-1 flex-col overflow-hidden">
          {!fullView && <Topbar />}
          <main className={fullView ? "flex-1 overflow-hidden" : "flex-1 overflow-y-auto p-6"}>
            <Outlet />
          </main>
        </div>
      </div>
    </PageTitleProvider>
  );
}
