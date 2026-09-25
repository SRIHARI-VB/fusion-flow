import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "./api-client";
import type { SidebarLayout } from "../components/layout/sidebar-layout";

/**
 * Per-user sidebar customization (custom groups, reordering, archiving) -
 * talks to the per-user sidebar-layout storage API. `null` means the user
 * has no saved customization yet, in which case callers should render
 * `navGroups` unchanged (see `computeEffectiveNav(baseGroups, null)` in
 * `components/layout/sidebar-layout.ts`).
 */

const SIDEBAR_LAYOUT_PATH = "/api/v1/users/me/sidebar-layout";

export const sidebarLayoutKeys = {
  layout: ["sidebar-layout"] as const,
};

interface SidebarLayoutEnvelope {
  layout: SidebarLayout | null;
}

async function fetchSidebarLayout(): Promise<SidebarLayout | null> {
  // Backend wraps the response as {"layout": ...}, never a bare layout -
  // see backend/src/fusionflow/modules/users/router.py.
  const { data } = await apiClient.get<SidebarLayoutEnvelope>(SIDEBAR_LAYOUT_PATH);
  return data.layout ?? null;
}

async function saveSidebarLayout(layout: SidebarLayout): Promise<SidebarLayout | null> {
  const { data } = await apiClient.put<SidebarLayoutEnvelope>(SIDEBAR_LAYOUT_PATH, { layout });
  return data.layout ?? null;
}

export function useSidebarLayout() {
  const { data, isLoading } = useQuery({
    queryKey: sidebarLayoutKeys.layout,
    queryFn: fetchSidebarLayout,
  });
  return { layout: data ?? null, isLoading };
}

export function useSaveSidebarLayout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: saveSidebarLayout,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: sidebarLayoutKeys.layout });
    },
  });
}
