import { apiClient } from "../../lib/api-client";
import type {
  Coupon,
  CouponCreateInput,
  CouponUpdateInput,
  Offer,
  OfferCreateInput,
  OfferUpdateInput,
  ProductService,
  ProductServiceCreateInput,
  ProductServiceType,
  ProductServiceUpdateInput,
} from "./types";

// ---------------------------------------------------------------------------
// Products / services — same backend table, one router per entity_type
// (see fusionflow.modules.catalog.router._build_product_service_router).
// ---------------------------------------------------------------------------

function productServiceBase(entityType: ProductServiceType): string {
  return entityType === "product" ? "/api/v1/products" : "/api/v1/services";
}

export async function listProductsServices(entityType: ProductServiceType): Promise<ProductService[]> {
  const { data } = await apiClient.get<ProductService[]>(productServiceBase(entityType));
  return data;
}

export async function createProductService(payload: ProductServiceCreateInput): Promise<ProductService> {
  const { data } = await apiClient.post<ProductService>(productServiceBase(payload.entity_type), payload);
  return data;
}

export async function updateProductService(
  entityType: ProductServiceType,
  id: string,
  payload: ProductServiceUpdateInput,
): Promise<ProductService> {
  const { data } = await apiClient.patch<ProductService>(`${productServiceBase(entityType)}/${id}`, payload);
  return data;
}

export async function deleteProductService(entityType: ProductServiceType, id: string): Promise<void> {
  await apiClient.delete(`${productServiceBase(entityType)}/${id}`);
}

// ---------------------------------------------------------------------------
// Coupons
// ---------------------------------------------------------------------------

const COUPONS_BASE = "/api/v1/coupons";

export async function listCoupons(): Promise<Coupon[]> {
  const { data } = await apiClient.get<Coupon[]>(COUPONS_BASE);
  return data;
}

export async function createCoupon(payload: CouponCreateInput): Promise<Coupon> {
  const { data } = await apiClient.post<Coupon>(COUPONS_BASE, payload);
  return data;
}

export async function updateCoupon(id: string, payload: CouponUpdateInput): Promise<Coupon> {
  const { data } = await apiClient.patch<Coupon>(`${COUPONS_BASE}/${id}`, payload);
  return data;
}

export async function deleteCoupon(id: string): Promise<void> {
  await apiClient.delete(`${COUPONS_BASE}/${id}`);
}

// ---------------------------------------------------------------------------
// Offers
// ---------------------------------------------------------------------------

const OFFERS_BASE = "/api/v1/offers";

export async function listOffers(): Promise<Offer[]> {
  const { data } = await apiClient.get<Offer[]>(OFFERS_BASE);
  return data;
}

export async function createOffer(payload: OfferCreateInput): Promise<Offer> {
  const { data } = await apiClient.post<Offer>(OFFERS_BASE, payload);
  return data;
}

export async function updateOffer(id: string, payload: OfferUpdateInput): Promise<Offer> {
  const { data } = await apiClient.patch<Offer>(`${OFFERS_BASE}/${id}`, payload);
  return data;
}

export async function deleteOffer(id: string): Promise<void> {
  await apiClient.delete(`${OFFERS_BASE}/${id}`);
}
