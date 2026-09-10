import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { Plus, RefreshCw, Trash2 } from "lucide-react";
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
import type { ConnectorInstance } from "../types";
import {
  createWhatsAppTemplate,
  deleteWhatsAppTemplate,
  fetchWhatsAppTemplates,
  syncWhatsAppTemplates,
  type WhatsAppTemplateCategory,
  type WhatsAppTemplateCreateRequest,
} from "./whatsapp-templates-api";

/**
 * The first registered entry in `registry.ts`'s per-connector settings
 * map - WhatsApp message template management: list what's known locally,
 * add one manually, or sync approved templates from Meta. This is the
 * home for what the `whatsapp.send_template` workflow node's config
 * picker will read from.
 */

const CATEGORY_BADGE: Record<WhatsAppTemplateCategory, "default" | "secondary" | "outline"> = {
  marketing: "default",
  utility: "secondary",
  authentication: "outline",
};

const EMPTY_FORM: WhatsAppTemplateCreateRequest = {
  name: "",
  language: "en_US",
  category: "utility",
  status: "approved",
  components: {},
};

export function WhatsAppSettingsPanel({ instance }: { instance: ConnectorInstance }) {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<WhatsAppTemplateCreateRequest>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);

  const queryKey = ["whatsapp-templates", instance.id];
  const { data: templates, isLoading } = useQuery({
    queryKey,
    queryFn: () => fetchWhatsAppTemplates(instance.id),
  });

  const createMutation = useMutation({
    mutationFn: () => createWhatsAppTemplate(instance.id, form),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey });
      setShowForm(false);
      setForm(EMPTY_FORM);
      setFormError(null);
    },
    onError: (err) => {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setFormError(axiosErr.response?.data?.detail ?? "Failed to create template.");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (templateId: string) => deleteWhatsAppTemplate(instance.id, templateId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey }),
  });

  const syncMutation = useMutation({
    mutationFn: () => syncWhatsAppTemplates(instance.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey }),
  });

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-2">
        <div>
          <CardTitle>Message templates</CardTitle>
          <p className="text-sm text-muted-foreground">
            Marketing/utility/authentication templates approved for this WhatsApp number - what the "Send
            WhatsApp Template" workflow node picks from.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => syncMutation.mutate()} disabled={syncMutation.isPending}>
            <RefreshCw className="h-3.5 w-3.5" />
            {syncMutation.isPending ? "Syncing..." : "Sync from Meta"}
          </Button>
          <Button size="sm" onClick={() => setShowForm((s) => !s)}>
            <Plus className="h-3.5 w-3.5" />
            Add template
          </Button>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {showForm && (
          <form
            className="flex flex-col gap-3 rounded-md border border-border p-3"
            onSubmit={(e) => {
              e.preventDefault();
              createMutation.mutate();
            }}
          >
            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-foreground" htmlFor="tpl-name">
                  Name
                </label>
                <Input
                  id="tpl-name"
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                  placeholder="order_confirmation"
                  required
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-foreground" htmlFor="tpl-language">
                  Language
                </label>
                <Input
                  id="tpl-language"
                  value={form.language}
                  onChange={(e) => setForm((f) => ({ ...f, language: e.target.value }))}
                  placeholder="en_US"
                  required
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-foreground" htmlFor="tpl-category">
                  Category
                </label>
                <select
                  id="tpl-category"
                  className="h-10 rounded-md border border-input bg-card px-3 text-sm text-foreground"
                  value={form.category}
                  onChange={(e) => setForm((f) => ({ ...f, category: e.target.value as WhatsAppTemplateCategory }))}
                >
                  <option value="marketing">Marketing</option>
                  <option value="utility">Utility</option>
                  <option value="authentication">Authentication</option>
                </select>
              </div>
            </div>
            {formError && <p className="text-sm text-destructive">{formError}</p>}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" size="sm" onClick={() => setShowForm(false)}>
                Cancel
              </Button>
              <Button type="submit" size="sm" disabled={createMutation.isPending}>
                Save
              </Button>
            </div>
          </form>
        )}

        {isLoading && <p className="text-sm text-muted-foreground">Loading templates...</p>}

        {!isLoading && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Language</TableHead>
                <TableHead>Category</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-12" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {(templates ?? []).map((template) => (
                <TableRow key={template.id}>
                  <TableCell className="font-medium text-foreground">{template.name}</TableCell>
                  <TableCell className="text-muted-foreground">{template.language}</TableCell>
                  <TableCell>
                    <Badge variant={CATEGORY_BADGE[template.category]}>{template.category}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant={template.status === "approved" ? "success" : "secondary"}>
                      {template.status}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => deleteMutation.mutate(template.id)}
                      disabled={deleteMutation.isPending}
                    >
                      <Trash2 className="h-3.5 w-3.5 text-destructive" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {(templates ?? []).length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="py-6 text-center text-sm text-muted-foreground">
                    No templates yet - add one manually or sync from Meta.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
