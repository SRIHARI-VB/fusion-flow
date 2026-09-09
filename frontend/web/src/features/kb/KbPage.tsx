import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Pencil, Plus, Trash2, X } from "lucide-react";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
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
import { createArticle, deleteArticle, listArticles, updateArticle } from "./api";
import type { KbArticle, KbArticleStatus } from "./types";

const articleSchema = z.object({
  title: z.string().min(1, "Title is required"),
  tags: z.string().optional(),
  body: z.string().min(1, "Body is required"),
  published: z.boolean(),
});

type ArticleFormValues = z.infer<typeof articleSchema>;

function toTagsArray(tags: string | undefined): string[] {
  return tags
    ? tags
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean)
    : [];
}

export function KbPage() {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<KbArticle | null>(null);
  const [formOpen, setFormOpen] = useState(false);

  const { data: articles = [], isLoading } = useQuery({ queryKey: ["kb-articles"], queryFn: listArticles });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ArticleFormValues>({
    resolver: zodResolver(articleSchema),
    defaultValues: { title: "", tags: "", body: "", published: false },
  });

  function closeForm() {
    setFormOpen(false);
    setEditing(null);
  }

  const createMutation = useMutation({
    mutationFn: createArticle,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["kb-articles"] });
      closeForm();
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Parameters<typeof updateArticle>[1] }) =>
      updateArticle(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["kb-articles"] });
      closeForm();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteArticle,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["kb-articles"] }),
  });

  function openCreate() {
    setEditing(null);
    reset({ title: "", tags: "", body: "", published: false });
    setFormOpen(true);
  }

  function openEdit(article: KbArticle) {
    setEditing(article);
    reset({
      title: article.title,
      tags: article.tags.join(", "),
      body: article.body,
      published: article.status === "published",
    });
    setFormOpen(true);
  }

  function onSubmit(values: ArticleFormValues) {
    const status: KbArticleStatus = values.published ? "published" : "draft";
    const payload = { title: values.title, body: values.body, tags: toTagsArray(values.tags), status };
    if (editing) {
      updateMutation.mutate({ id: editing.id, payload });
    } else {
      createMutation.mutate(payload);
    }
  }

  const saving = createMutation.isPending || updateMutation.isPending;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Knowledge Base</h1>
          <p className="text-sm text-muted-foreground">
            Help articles your customers and support agent can reference.
          </p>
        </div>
        <Button onClick={openCreate}>
          <Plus className="h-4 w-4" />
          New Article
        </Button>
      </div>

      {formOpen && (
        <Card>
          <CardHeader>
            <CardTitle>{editing ? "Edit article" : "New article"}</CardTitle>
            <CardDescription>Write a knowledge base article for your team or customers.</CardDescription>
          </CardHeader>
          <CardContent>
            <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="title" className="text-sm font-medium">
                  Title
                </label>
                <Input id="title" error={!!errors.title} {...register("title")} />
                {errors.title && <p className="text-xs text-destructive">{errors.title.message}</p>}
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="tags" className="text-sm font-medium">
                  Tags (comma separated)
                </label>
                <Input id="tags" placeholder="billing, refunds" {...register("tags")} />
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="body" className="text-sm font-medium">
                  Body
                </label>
                <textarea
                  id="body"
                  rows={8}
                  className="rounded-md border border-input bg-card p-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  {...register("body")}
                />
                {errors.body && <p className="text-xs text-destructive">{errors.body.message}</p>}
              </div>
              <label className="flex items-center gap-2 text-sm font-medium">
                <input type="checkbox" className="h-4 w-4" {...register("published")} />
                Published
              </label>
              <div className="flex items-center gap-2">
                <Button type="submit" disabled={saving}>
                  {saving ? "Saving..." : editing ? "Save changes" : "Create article"}
                </Button>
                <Button type="button" variant="outline" onClick={closeForm}>
                  <X className="h-4 w-4" />
                  Cancel
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead>Tags</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-muted-foreground">
                  Loading...
                </TableCell>
              </TableRow>
            )}
            {!isLoading && articles.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-muted-foreground">
                  No articles yet.
                </TableCell>
              </TableRow>
            )}
            {articles.map((article) => (
              <TableRow key={article.id}>
                <TableCell className="font-medium text-foreground">{article.title}</TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-1">
                    {article.tags.map((tag) => (
                      <Badge key={tag} variant="outline">
                        {tag}
                      </Badge>
                    ))}
                  </div>
                </TableCell>
                <TableCell>
                  <Badge variant={article.status === "published" ? "success" : "secondary"}>
                    {article.status}
                  </Badge>
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-2">
                    <Button variant="ghost" size="icon" onClick={() => openEdit(article)} aria-label="Edit">
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => deleteMutation.mutate(article.id)}
                      aria-label="Delete"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
