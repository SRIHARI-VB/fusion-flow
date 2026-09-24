import { useQuery } from "@tanstack/react-query";
import { listProductsServices } from "./api";
import type { ProductService } from "./types";

export interface AppliesTo {
  service_ids: string[];
  product_ids: string[];
  // Index signature so `AppliesTo` values can be assigned directly into the
  // `applies_to: Record<string, unknown>` field on `Offer`/`Coupon` payloads.
  [key: string]: unknown;
}

export const EMPTY_APPLIES_TO: AppliesTo = { service_ids: [], product_ids: [] };

/** Coerces a freeform `applies_to` JSONB value (possibly `{}`/stale shape) into the picker's shape. */
export function toAppliesTo(raw: Record<string, unknown> | null | undefined): AppliesTo {
  const serviceIds = Array.isArray(raw?.service_ids) ? (raw!.service_ids as string[]) : [];
  const productIds = Array.isArray(raw?.product_ids) ? (raw!.product_ids as string[]) : [];
  return { service_ids: serviceIds, product_ids: productIds };
}

/** Short "N services, N products" (or "All" when unrestricted) label for list tables. */
export function appliesToSummary(raw: Record<string, unknown> | null | undefined): string {
  const { service_ids: serviceIds, product_ids: productIds } = toAppliesTo(raw);
  const parts: string[] = [];
  if (serviceIds.length > 0) parts.push(`${serviceIds.length} service${serviceIds.length === 1 ? "" : "s"}`);
  if (productIds.length > 0) parts.push(`${productIds.length} product${productIds.length === 1 ? "" : "s"}`);
  return parts.length > 0 ? parts.join(", ") : "All";
}

interface ServiceProductPickerProps {
  value: AppliesTo;
  onChange: (next: AppliesTo) => void;
}

function CheckboxGroup({
  title,
  items,
  selectedIds,
  onToggle,
}: {
  title: string;
  items: ProductService[];
  selectedIds: string[];
  onToggle: (id: string) => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{title}</p>
      <div className="flex max-h-48 flex-col gap-1.5 overflow-y-auto rounded-md border border-input p-2">
        {items.length === 0 && <p className="text-xs text-muted-foreground">None yet.</p>}
        {items.map((item) => (
          <label key={item.id} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-input"
              checked={selectedIds.includes(item.id)}
              onChange={() => onToggle(item.id)}
            />
            <span className="text-foreground">{item.name}</span>
            <span className="text-xs text-muted-foreground">{item.base_price}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

/**
 * Multi-select picker for the `applies_to` field shared by offers and coupons
 * (`{ service_ids: string[], product_ids: string[] }`). Fetches the tenant's
 * services/products itself so both `OffersPage` and `CouponsPage` can drop it
 * in without duplicating the fetch. An empty selection means "applies to
 * everything" — see `appliesToSummary`.
 */
export function ServiceProductPicker({ value, onChange }: ServiceProductPickerProps) {
  const { data: services = [] } = useQuery({
    queryKey: ["products-services", "service"],
    queryFn: () => listProductsServices("service"),
  });
  const { data: products = [] } = useQuery({
    queryKey: ["products-services", "product"],
    queryFn: () => listProductsServices("product"),
  });

  function toggleService(id: string) {
    const serviceIds = value.service_ids.includes(id)
      ? value.service_ids.filter((existing) => existing !== id)
      : [...value.service_ids, id];
    onChange({ ...value, service_ids: serviceIds });
  }

  function toggleProduct(id: string) {
    const productIds = value.product_ids.includes(id)
      ? value.product_ids.filter((existing) => existing !== id)
      : [...value.product_ids, id];
    onChange({ ...value, product_ids: productIds });
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <CheckboxGroup title="Services" items={services} selectedIds={value.service_ids} onToggle={toggleService} />
      <CheckboxGroup title="Products" items={products} selectedIds={value.product_ids} onToggle={toggleProduct} />
    </div>
  );
}
