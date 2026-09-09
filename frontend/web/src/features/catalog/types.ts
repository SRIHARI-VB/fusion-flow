/** Mirrors `fusionflow.modules.catalog.schemas` on the backend. */
import type { CustomFieldsValue } from "../custom-fields/types";

export type ProductServiceType = "product" | "service";
export type DiscountType = "percentage" | "fixed_amount";

export interface ProductService {
  id: string;
  entity_type: ProductServiceType;
  name: string;
  description: string | null;
  base_price: string;
  is_active: boolean;
  custom_fields: CustomFieldsValue;
  created_at: string;
  updated_at: string;
}

export interface ProductServiceCreateInput {
  entity_type: ProductServiceType;
  name: string;
  description?: string | null;
  base_price: number;
  is_active?: boolean;
  custom_fields?: CustomFieldsValue;
}

export type ProductServiceUpdateInput = Partial<Omit<ProductServiceCreateInput, "entity_type">>;

export interface Coupon {
  id: string;
  code: string;
  discount_type: DiscountType;
  discount_value: string;
  valid_from: string | null;
  valid_to: string | null;
  usage_limit: number | null;
  custom_fields: CustomFieldsValue;
  created_at: string;
  updated_at: string;
}

export interface CouponCreateInput {
  code: string;
  discount_type: DiscountType;
  discount_value: number;
  valid_from?: string | null;
  valid_to?: string | null;
  usage_limit?: number | null;
  custom_fields?: CustomFieldsValue;
}

export type CouponUpdateInput = Partial<CouponCreateInput>;

export interface Offer {
  id: string;
  name: string;
  applies_to: Record<string, unknown>;
  custom_fields: CustomFieldsValue;
  active_from: string | null;
  active_to: string | null;
  created_at: string;
  updated_at: string;
}

export interface OfferCreateInput {
  name: string;
  applies_to?: Record<string, unknown>;
  custom_fields?: CustomFieldsValue;
  active_from?: string | null;
  active_to?: string | null;
}

export type OfferUpdateInput = Partial<OfferCreateInput>;
