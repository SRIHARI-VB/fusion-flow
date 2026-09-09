import { useQuery } from "@tanstack/react-query";
import { FileWarning } from "lucide-react";
import {
  Badge,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@fusion-flow/ui";
import { templatesAvailable } from "../../lib/admin-types";
import { fetchTemplates } from "../../lib/endpoints";

export function TemplatesPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin", "templates"],
    queryFn: fetchTemplates,
  });

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Global field templates</h1>
        <p className="text-sm text-muted-foreground">
          Platform-seeded starter field sets per vertical. Read-only for now - authoring UI ships once
          template editing is wired up on the backend.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Templates</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading && <p className="py-8 text-center text-sm text-muted-foreground">Loading…</p>}
          {isError && (
            <p className="py-8 text-center text-sm text-destructive">Could not load templates.</p>
          )}
          {!isLoading && !isError && data && !templatesAvailable(data) && (
            <div className="flex flex-col items-center gap-2 py-10 text-center">
              <FileWarning className="h-8 w-8 text-muted-foreground" />
              <CardDescription>{data.reason}</CardDescription>
            </div>
          )}
          {!isLoading && !isError && data && templatesAvailable(data) && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Vertical</TableHead>
                  <TableHead>Entity type</TableHead>
                  <TableHead>Fields</TableHead>
                  <TableHead>Version</TableHead>
                  <TableHead>Scope</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.map((tpl) => (
                  <TableRow key={tpl.id}>
                    <TableCell className="font-medium text-foreground">{tpl.name}</TableCell>
                    <TableCell className="text-muted-foreground">{tpl.vertical}</TableCell>
                    <TableCell className="capitalize">{tpl.entity_type}</TableCell>
                    <TableCell>{tpl.field_count}</TableCell>
                    <TableCell>v{tpl.version}</TableCell>
                    <TableCell>
                      <Badge variant={tpl.is_global ? "default" : "secondary"}>
                        {tpl.is_global ? "Global" : "Scoped"}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
                {data.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6} className="py-8 text-center text-sm text-muted-foreground">
                      No templates seeded yet.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
