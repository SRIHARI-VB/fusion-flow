import { apiClient } from "../../lib/api-client";
import { getCustomer } from "../customers/api";
import type { Customer } from "../customers/types";
import type { ObjectFieldDefinition, ObjectRecord, ObjectType } from "./types";

const BASE = "/api/v1/business-objects";

// ---------------------------------------------------------------------------
// Business-object types / field definitions / records
// (see fusionflow.modules.business_objects.router)
// ---------------------------------------------------------------------------

/**
 * Resolves a tenant's business-object type by its `key` (e.g. "appointment").
 * The backend only exposes get-by-id (`GET /types/{type_id}`) plus a
 * get-by-key resolver internal to the `/types/{key}/records` routes - there's
 * no `GET /types/by-key/{key}` - so we list all of the tenant's types and
 * find the match ourselves. Tenants have few object types, so this is cheap.
 */
export async function fetchObjectType(typeKey: string): Promise<ObjectType> {
  const { data } = await apiClient.get<ObjectType[]>(`${BASE}/types`);
  const found = data.find((type) => type.key === typeKey);
  if (!found) {
    throw new Error(`Object type "${typeKey}" not found`);
  }
  return found;
}

export async function listObjectFieldDefinitions(typeId: string): Promise<ObjectFieldDefinition[]> {
  const { data } = await apiClient.get<ObjectFieldDefinition[]>(`${BASE}/types/${typeId}/fields`);
  return data;
}

/**
 * Lists records for a type by its `key`. The backend's `GET
 * /types/{key}/records` has no pagination/filter query params today (see
 * `business_objects/router.py::list_records`) - it always returns the
 * tenant's full set for that type, so there's nothing to pass through yet.
 */
export async function listObjectRecords(typeKey: string): Promise<ObjectRecord[]> {
  const { data } = await apiClient.get<ObjectRecord[]>(`${BASE}/types/${typeKey}/records`);
  return data;
}

// ---------------------------------------------------------------------------
// Customer lookups - `features/customers` only exposes single-id lookup
// (`getCustomer`), no batch endpoint, so we fan out with `Promise.all`,
// dedupe by id, and cache resolved (and not-found) results in a module-level
// Map. Fine for an admin page with modest row counts.
// ---------------------------------------------------------------------------

const customerCache = new Map<string, Customer | null>();

export async function getCustomersByIds(ids: string[]): Promise<Map<string, Customer | null>> {
  const uniqueIds = Array.from(new Set(ids.filter((id): id is string => Boolean(id))));
  const missingIds = uniqueIds.filter((id) => !customerCache.has(id));

  await Promise.all(
    missingIds.map(async (id) => {
      try {
        const customer = await getCustomer(id);
        customerCache.set(id, customer);
      } catch {
        customerCache.set(id, null);
      }
    }),
  );

  const result = new Map<string, Customer | null>();
  for (const id of uniqueIds) {
    result.set(id, customerCache.get(id) ?? null);
  }
  return result;
}
