import { apiClient } from "../../lib/api-client";
import type { Order, OrderCreateInput, OrderUpdateInput } from "./types";

const BASE = "/api/v1/orders";

export async function listOrders(): Promise<Order[]> {
  const { data } = await apiClient.get<Order[]>(BASE);
  return data;
}

export async function getOrder(id: string): Promise<Order> {
  const { data } = await apiClient.get<Order>(`${BASE}/${id}`);
  return data;
}

export async function createOrder(payload: OrderCreateInput): Promise<Order> {
  const { data } = await apiClient.post<Order>(BASE, payload);
  return data;
}

export async function updateOrder(id: string, payload: OrderUpdateInput): Promise<Order> {
  const { data } = await apiClient.patch<Order>(`${BASE}/${id}`, payload);
  return data;
}
