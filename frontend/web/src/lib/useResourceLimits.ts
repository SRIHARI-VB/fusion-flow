import { useQuery } from "@tanstack/react-query";
import { fetchResourceUsage } from "./endpoints";

/**
 * Per-resource `{limit, current}` for the active tenant - drives the "42 /
 * 50" usage badge and the disabled state on each "New X" button. Purely a
 * UX nicety: the backend 403s the create route independently
 * (`enforce_resource_limit`) regardless of what this hook returns.
 */
export function useResourceLimits() {
  const { data, isLoading } = useQuery({
    queryKey: ["resource-usage"],
    queryFn: fetchResourceUsage,
  });

  function usage(resourceKey: string) {
    const entry = data?.[resourceKey];
    const atLimit = entry?.limit != null && entry.current >= entry.limit;
    return { limit: entry?.limit ?? null, current: entry?.current ?? 0, atLimit };
  }

  return { usage, isLoading };
}
