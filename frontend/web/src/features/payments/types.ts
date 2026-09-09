/** Mirrors `fusionflow.modules.payments.schemas` on the backend. */
export type PaymentStatus = "pending" | "succeeded" | "failed" | "refunded";

export interface Payment {
  id: string;
  order_id: string | null;
  customer_id: string;
  connector_instance_id: string | null;
  provider_ref: string | null;
  amount: number;
  currency: string;
  status: PaymentStatus;
  raw_event_ref: string | null;
  created_at: string;
}
