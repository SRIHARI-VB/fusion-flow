import type {
  AuthTokens,
  Business,
  LoginRequest,
  SignupRequest,
  SignupResult,
  User,
} from "@fusion-flow/ts-types";
import { apiClient } from "./api-client";

export async function signup(payload: SignupRequest): Promise<SignupResult> {
  const { data } = await apiClient.post<SignupResult>("/api/v1/auth/signup", payload);
  return data;
}

export async function login(payload: LoginRequest): Promise<AuthTokens> {
  const { data } = await apiClient.post<AuthTokens>("/api/v1/auth/login", payload);
  return data;
}

export async function logout(): Promise<void> {
  await apiClient.post("/api/v1/auth/logout");
}

export async function fetchMe(): Promise<User> {
  const { data } = await apiClient.get<User>("/api/v1/auth/me");
  return data;
}

export async function fetchMyBusinesses(): Promise<Business[]> {
  const { data } = await apiClient.get<Business[]>("/api/v1/businesses/mine");
  return data;
}

export interface StepUpResult {
  step_up_token: string;
  expires_at: string;
}

/** Doctor-only re-authentication for the clinic-queue module - see
 * `useStepUpAuth`/`RequireStepUp`. Rejects with a 401 on the wrong password. */
export async function confirmStepUpPassword(password: string): Promise<StepUpResult> {
  const { data } = await apiClient.post<StepUpResult>("/api/v1/auth/step-up", { password });
  return data;
}

export interface ResourceUsageEntry {
  limit: number | null;
  current: number;
}

/** `{resource_key: {limit, current}}` for every limitable resource - backs
 * `useResourceLimits()`. The backend 403 on the actual create route is the
 * real enforcement boundary; this only drives the UI's usage badge/disabled
 * state.
 *
 * `customFieldsEntityType` is required to get a `custom_fields` entry back
 * at all - that limit applies per entity_type (product/service/coupon/
 * offer), not once per tenant, so the caller must say which tab it means. */
export async function fetchResourceUsage(
  customFieldsEntityType?: string,
): Promise<Record<string, ResourceUsageEntry>> {
  const { data } = await apiClient.get<Record<string, ResourceUsageEntry>>(
    "/api/v1/businesses/mine/resource-usage",
    { params: customFieldsEntityType ? { custom_fields_entity_type: customFieldsEntityType } : undefined },
  );
  return data;
}

export async function switchBusiness(businessId: string): Promise<AuthTokens> {
  const { data } = await apiClient.post<AuthTokens>(`/api/v1/businesses/${businessId}/switch`);
  return data;
}

export async function selectBusiness(businessId: string): Promise<AuthTokens> {
  const { data } = await apiClient.post<AuthTokens>("/api/v1/auth/select-business", {
    business_id: businessId,
  });
  return data;
}
