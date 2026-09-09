import { apiClient } from "../../lib/api-client";
import type { Customer, CustomerCreateInput, CustomerUpdateInput } from "./types";

const BASE = "/api/v1/customers";

export async function listCustomers(): Promise<Customer[]> {
  const { data } = await apiClient.get<Customer[]>(BASE);
  return data;
}

export async function getCustomer(id: string): Promise<Customer> {
  const { data } = await apiClient.get<Customer>(`${BASE}/${id}`);
  return data;
}

export async function createCustomer(payload: CustomerCreateInput): Promise<Customer> {
  const { data } = await apiClient.post<Customer>(BASE, payload);
  return data;
}

export async function updateCustomer(id: string, payload: CustomerUpdateInput): Promise<Customer> {
  const { data } = await apiClient.patch<Customer>(`${BASE}/${id}`, payload);
  return data;
}

export async function deleteCustomer(id: string): Promise<void> {
  await apiClient.delete(`${BASE}/${id}`);
}
