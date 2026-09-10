import { useResourceLimits } from "../lib/useResourceLimits";

/**
 * Small "42 / 50" tag next to a "New X" button - renders nothing when the
 * resource has no configured limit (the common case), so pages stay
 * uncluttered for tenants nobody has capped. Purely informational; the
 * actual boundary is the backend 403 on the create route.
 */
export function ResourceUsageBadge({ resourceKey }: { resourceKey: string }) {
  const { usage } = useResourceLimits();
  const { limit, current } = usage(resourceKey);
  if (limit === null) return null;
  return (
    <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
      {current} / {limit}
    </span>
  );
}
