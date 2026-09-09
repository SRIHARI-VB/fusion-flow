import { MoreHorizontal, Search } from "lucide-react";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@fusion-flow/ui";

interface TenantRow {
  id: string;
  name: string;
  slug: string;
  vertical: string;
  status: "active" | "suspended" | "pending";
  createdAt: string;
}

const tenants: TenantRow[] = [
  { id: "biz_1", name: "Acme Retail", slug: "acme-retail", vertical: "E-commerce", status: "active", createdAt: "Aug 12, 2026" },
  { id: "biz_2", name: "Northwind Clinic", slug: "northwind-clinic", vertical: "Healthcare", status: "active", createdAt: "Aug 20, 2026" },
  { id: "biz_3", name: "Zenith Studio", slug: "zenith-studio", vertical: "Services", status: "pending", createdAt: "Sep 01, 2026" },
  { id: "biz_4", name: "Blue Harbor Cafe", slug: "blue-harbor-cafe", vertical: "Food & Beverage", status: "suspended", createdAt: "Jul 30, 2026" },
];

const statusVariant: Record<TenantRow["status"], "success" | "secondary" | "destructive"> = {
  active: "success",
  pending: "secondary",
  suspended: "destructive",
};

export function TenantsPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Tenants</h1>
        <p className="text-sm text-muted-foreground">
          All businesses on the platform. Mock data — proves the shared @fusion-flow/ui package
          works identically in frontend/admin.
        </p>
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between gap-4">
          <CardTitle>All tenants</CardTitle>
          <div className="relative hidden sm:block">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input placeholder="Search tenants" className="h-9 w-56 pl-8 text-sm" />
          </div>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Business</TableHead>
                <TableHead>Slug</TableHead>
                <TableHead>Vertical</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Created</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {tenants.map((tenant) => (
                <TableRow key={tenant.id}>
                  <TableCell className="font-medium text-foreground">{tenant.name}</TableCell>
                  <TableCell className="text-muted-foreground">{tenant.slug}</TableCell>
                  <TableCell>{tenant.vertical}</TableCell>
                  <TableCell>
                    <Badge variant={statusVariant[tenant.status]}>{tenant.status}</Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{tenant.createdAt}</TableCell>
                  <TableCell>
                    <Button variant="ghost" size="icon" aria-label={`Actions for ${tenant.name}`}>
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
