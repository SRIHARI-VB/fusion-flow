/** Mirrors `fusionflow.modules.customers.schemas` on the backend. */
export interface Customer {
  id: string;
  external_ref: string | null;
  name: string;
  email: string | null;
  phone: string | null;
  custom_fields: Record<string, unknown>;
  created_at: string;
}

export interface CustomerCreateInput {
  external_ref?: string | null;
  name: string;
  email?: string | null;
  phone?: string | null;
  custom_fields?: Record<string, unknown>;
}

export type CustomerUpdateInput = Partial<CustomerCreateInput>;
