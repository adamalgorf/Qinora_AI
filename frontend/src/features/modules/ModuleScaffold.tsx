import { type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

type ModuleScaffoldProps = {
  title: string;
  description: string;
  badge: string;
  children: ReactNode;
};

export function ModuleScaffold({ title, description, badge, children }: ModuleScaffoldProps) {
  return (
    <section className="module-page">
      <header className="module-header">
        <Badge className="border-primary/30 bg-primary/10 text-primary" variant="outline">
          {badge}
        </Badge>
        <h1>{title}</h1>
        <p className="page-lede">{description}</p>
      </header>
      <Card className="data-card">
        <CardContent className="pt-5">{children}</CardContent>
      </Card>
    </section>
  );
}
