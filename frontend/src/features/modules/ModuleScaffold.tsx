import { type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

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
        <Badge className="border-cyan-400/30 bg-cyan-400/10 text-cyan-200" variant="outline">
          {badge}
        </Badge>
        <h1>{title}</h1>
        <p className="page-lede">{description}</p>
      </header>
      <Card className="data-card">
        <CardHeader>
          <CardDescription>Live API data</CardDescription>
          <CardTitle>Operational records</CardTitle>
        </CardHeader>
        <CardContent>{children}</CardContent>
      </Card>
    </section>
  );
}
