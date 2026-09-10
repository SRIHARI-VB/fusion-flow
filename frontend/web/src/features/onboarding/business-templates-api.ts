import { apiClient } from "../../lib/api-client";

/**
 * Mirrors `backend/src/fusionflow/modules/business_templates/schemas.py`.
 *
 * A `BusinessTemplate` is a higher-level "starter kit" (a connector bundle
 * + optional plan) - distinct from the older, narrower per-entity-type
 * `FieldTemplate` concept in `../custom-fields` (see that module's own
 * `FieldTemplate` type). The onboarding "template" step now applies both:
 * this template's connector bundle (granted server-side the moment
 * `applyBusinessTemplate` is called) and the matching `FieldTemplate`s for
 * the same `vertical`, via the existing custom-fields `applyFieldTemplate`
 * call.
 */
export interface BusinessTemplate {
  id: string;
  key: string;
  name: string;
  description: string | null;
  vertical: string | null;
  plan_id: string | null;
  is_active: boolean;
  connector_type_keys: string[];
}

export interface ApplyBusinessTemplateResponse {
  business_template_id: string;
  vertical: string | null;
}

const BASE = "/api/v1/business-templates";

/** `GET /api/v1/business-templates` — active templates, tenant-authenticated. */
export async function listBusinessTemplates(): Promise<BusinessTemplate[]> {
  const { data } = await apiClient.get<BusinessTemplate[]>(BASE);
  return data;
}

/**
 * `POST /api/v1/business-templates/{id}/apply` — records
 * `Business.business_template_id` (and `plan_id`, if unset) and returns the
 * template's `vertical` so the caller can apply its matching
 * `FieldTemplate`s next.
 */
export async function applyBusinessTemplate(templateId: string): Promise<ApplyBusinessTemplateResponse> {
  const { data } = await apiClient.post<ApplyBusinessTemplateResponse>(`${BASE}/${templateId}/apply`);
  return data;
}
