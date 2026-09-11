import { useState } from "react";
import { X } from "lucide-react";
import { Button, Input } from "@fusion-flow/ui";

/**
 * "Save as Component" — a small floating panel (same overlay treatment
 * `WorkflowEditorPage.tsx`'s own test-run panel already uses, no dialog
 * primitive exists in `@fusion-flow/ui`) offered whenever 1+ nodes are
 * currently selected on the canvas. Saves that selection as a reusable
 * `WorkflowUserComponent` the author (and only this tenant) can insert
 * into any other workflow afterward via `ComponentPicker.tsx`.
 */

interface SaveComponentDialogProps {
  nodeCount: number;
  onSave: (payload: { name: string; description: string | null; category: string | null; icon: string | null }) => void;
  onClose: () => void;
  isSaving?: boolean;
}

export function SaveComponentDialog({ nodeCount, onSave, onClose, isSaving }: SaveComponentDialogProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("");
  const [icon, setIcon] = useState("");

  function handleSave() {
    if (!name.trim()) return;
    onSave({
      name: name.trim(),
      description: description.trim() || null,
      category: category.trim() || null,
      icon: icon.trim() || null,
    });
  }

  return (
    <div className="absolute bottom-4 left-4 z-20 w-80 rounded-lg border border-border bg-card p-3 shadow-lg">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-sm font-semibold text-foreground">Save as Component</p>
        <button
          type="button"
          aria-label="Close"
          className="rounded-md p-1 text-muted-foreground hover:bg-muted"
          onClick={onClose}
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        Saves the {nodeCount} selected node{nodeCount === 1 ? "" : "s"} (and the connections between them) as a
        reusable fragment you can insert into any other workflow later.
      </p>

      <div className="flex flex-col gap-2">
        <div className="flex flex-col gap-1">
          <label htmlFor="component-name" className="text-xs font-medium text-foreground">
            Name <span className="text-destructive">*</span>
          </label>
          <Input id="component-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Coupon check" />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="component-description" className="text-xs font-medium text-foreground">
            Description
          </label>
          <Input
            id="component-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Optional"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="component-category" className="text-xs font-medium text-foreground">
            Category
          </label>
          <Input
            id="component-category"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            placeholder="Optional, e.g. Ecommerce"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="component-icon" className="text-xs font-medium text-foreground">
            Icon key
          </label>
          <Input
            id="component-icon"
            value={icon}
            onChange={(e) => setIcon(e.target.value)}
            placeholder="Optional, e.g. star"
          />
        </div>
      </div>

      <div className="mt-3 flex justify-end gap-2 border-t border-border pt-3">
        <Button type="button" variant="outline" size="sm" onClick={onClose}>
          Cancel
        </Button>
        <Button type="button" size="sm" onClick={handleSave} disabled={!name.trim() || isSaving}>
          {isSaving ? "Saving..." : "Save"}
        </Button>
      </div>
    </div>
  );
}
