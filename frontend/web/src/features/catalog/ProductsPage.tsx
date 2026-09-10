import { ProductServiceCatalogPage } from "./ProductServiceCatalogPage";

export function ProductsPage() {
  return (
    <ProductServiceCatalogPage
      entityType="product"
      resourceKey="products"
      title="Products"
      description="What you sell — with whatever custom fields your vertical needs."
      itemNoun="product"
    />
  );
}
