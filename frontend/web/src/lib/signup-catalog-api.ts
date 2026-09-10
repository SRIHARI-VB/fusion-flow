import type { BusinessTemplate } from "../features/onboarding/business-templates-api";
import type { ConnectorType } from "../features/connectors/types";
import { apiClient } from "./api-client";

/**
 * `GET /api/v1/business-templates/catalog` — the one genuinely
 * unauthenticated endpoint in the app: the signup form needs to show
 * starter-kit templates and the full connector/module catalog before any
 * session exists. `apiClient`'s request interceptor only attaches an
 * `Authorization` header when a token is present in the auth store (see
 * `api-client.ts`), so calling this pre-login is safe - it just sends no
 * header at all.
 */
export interface SignupCatalog {
  templates: BusinessTemplate[];
  connector_types: ConnectorType[];
}

export async function fetchSignupCatalog(): Promise<SignupCatalog> {
  const { data } = await apiClient.get<SignupCatalog>("/api/v1/business-templates/catalog");
  return data;
}
