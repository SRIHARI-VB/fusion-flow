import { useQuery } from "@tanstack/react-query";
import { fetchResourceUsage } from "./endpoints";

/**
 * Per-resource `{limit, current}` for the active tenant - drives the "42 /
 * 50" usage badge and the disabled state on each "New X" button. Purely a
 * UX nicety: the backend 403s the create route independently regardless of
 * what this hook returns.
 *
 * Pass `customFieldsEntityType` (the currently-open tab, e.g. "product")
 * when the caller cares about the `custom_fields` entry specifically -
 * that limit applies per entity_type, so there's no single tenant-wide
 * number to report without knowing which one you mean.
 */
export function useResourceLimits(customFieldsEntityType?: string) {
  const { data, isLoading } = useQuery({
    queryKey: ["resource-usage", customFieldsEntityType ?? null],
    queryFn: () => fetchResourceUsage(customFieldsEntityType),
  });

  function usage(resourceKey: string) {
    const entry = data?.[resourceKey];
    const atLimit = entry?.limit != null && entry.current >= entry.limit;
    return { limit: entry?.limit ?? null, current: entry?.current ?? 0, atLimit };
  }

  return { usage, isLoading };
}
