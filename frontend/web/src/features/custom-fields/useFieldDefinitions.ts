import { useQuery } from "@tanstack/react-query";
import { listFieldDefinitions } from "./api";
import type { CustomFieldEntityType } from "./types";

/**
 * Fetches the tenant's live `field_definitions` for one entity_type, so a
 * catalog page (products/services/coupons/offers) can build its custom
 * fields inputs at runtime instead of hardcoding a shape per vertical.
 */
export function useFieldDefinitions(entityType: CustomFieldEntityType) {
  return useQuery({
    queryKey: ["custom-fields", "definitions", entityType],
    queryFn: () => listFieldDefinitions(entityType),
  });
}
