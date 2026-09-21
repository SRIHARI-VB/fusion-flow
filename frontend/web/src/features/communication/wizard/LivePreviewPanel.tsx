import type { ReactNode } from "react";
import { ExternalLink } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@fusion-flow/ui";

/** "Target Content" panel - shows whatever the automation is being set up
 * against (a specific Instagram post's thumbnail+caption, a WhatsApp
 * number, ...) next to the form, so the tenant can see exactly what
 * they're configuring instead of trusting an id in a dropdown. */
interface LivePreviewPanelProps {
  title?: string;
  externalHref?: string;
  externalLabel?: string;
  children: ReactNode;
}

export function LivePreviewPanel({
  title = "Target Content",
  externalHref,
  externalLabel = "View",
  children,
}: LivePreviewPanelProps) {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="text-sm">{title}</CardTitle>
        {externalHref && (
          <a
            href={externalHref}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-xs text-accent hover:underline"
          >
            {externalLabel}
            <ExternalLink className="h-3 w-3" />
          </a>
        )}
      </CardHeader>
      <CardContent className="pt-0">{children}</CardContent>
    </Card>
  );
}
