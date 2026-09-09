import { Construction } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@fusion-flow/ui";

interface PlaceholderPageProps {
  title: string;
  description?: string;
}

export function PlaceholderPage({ title, description }: PlaceholderPageProps) {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">{title}</h1>
        <p className="text-sm text-muted-foreground">
          {description ?? "This area is planned but not built in this wave."}
        </p>
      </div>

      <Card>
        <CardHeader className="items-center text-center">
          <div className="mb-2 flex h-12 w-12 items-center justify-center rounded-full bg-accent-soft text-accent">
            <Construction className="h-6 w-6" />
          </div>
          <CardTitle>Coming soon</CardTitle>
          <CardDescription>
            {title} is scaffolded (route + nav entry) but the real feature ships in a later
            milestone per the phased roadmap.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex justify-center py-8 text-sm text-muted-foreground">
          Check back after this module's milestone lands.
        </CardContent>
      </Card>
    </div>
  );
}
