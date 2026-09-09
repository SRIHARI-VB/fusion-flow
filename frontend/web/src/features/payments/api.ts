import { apiClient } from "../../lib/api-client";
import type { Payment } from "./types";

const BASE = "/api/v1/payments";

export async function listPayments(): Promise<Payment[]> {
  const { data } = await apiClient.get<Payment[]>(BASE);
  return data;
}

export async function getPayment(id: string): Promise<Payment> {
  const { data } = await apiClient.get<Payment>(`${BASE}/${id}`);
  return data;
}
