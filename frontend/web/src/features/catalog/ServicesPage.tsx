import { ProductServiceCatalogPage } from "./ProductServiceCatalogPage";

export function ServicesPage() {
  return (
    <ProductServiceCatalogPage
      entityType="service"
      resourceKey="services"
      title="Services"
      description="What you offer — with whatever custom fields your vertical needs."
      itemNoun="service"
    />
  );
}
