import { Sparkles } from "lucide-react";

/** Green contextual-tips box - the "Suggested keywords are retrieved
 * from..." style callout from the Profiterasoft reference. */
interface TipsCalloutProps {
  tips: string[];
}

export function TipsCallout({ tips }: TipsCalloutProps) {
  if (tips.length === 0) return null;
  return (
    <div className="rounded-md border border-accent/30 bg-accent-soft p-3">
      <div className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-accent">
        <Sparkles className="h-3.5 w-3.5" />
        Tips
      </div>
      <ul className="flex flex-col gap-1 text-xs text-foreground">
        {tips.map((tip) => (
          <li key={tip}>• {tip}</li>
        ))}
      </ul>
    </div>
  );
}
