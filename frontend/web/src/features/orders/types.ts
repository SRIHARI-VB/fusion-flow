/** Mirrors `fusionflow.modules.orders.schemas` on the backend. */
export type OrderStatus = "pending" | "paid" | "fulfilled" | "cancelled";

export type LineItem = Record<string, unknown>;

export interface Order {
  id: string;
  customer_id: string;
  customer_name: string | null;
  status: OrderStatus;
  total_amount: number;
  currency: string;
  line_items: LineItem[];
  created_at: string;
  updated_at: string;
}

export interface OrderCreateInput {
  customer_id: string;
  status?: OrderStatus;
  total_amount?: number;
  currency?: string;
  line_items?: LineItem[];
}

export interface OrderUpdateInput {
  status?: OrderStatus;
  total_amount?: number;
  currency?: string;
  line_items?: LineItem[];
}
