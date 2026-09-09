import type { AuthTokens, LoginRequest } from "@fusion-flow/ts-types";
import { apiClient } from "./api-client";

export async function login(payload: LoginRequest): Promise<AuthTokens> {
  const { data } = await apiClient.post<AuthTokens>("/api/v1/auth/login", payload);
  return data;
}
