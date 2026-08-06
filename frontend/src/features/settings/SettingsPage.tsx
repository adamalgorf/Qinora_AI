import { Moon, Settings, Sun } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useTheme } from "@/shared/theme/ThemeProvider";
import { APP_VERSION } from "@/shared/version";

export function SettingsPage() {
  const { theme, setTheme } = useTheme();

  return (
    <section className="module-page">
      <header className="module-header">
        <Badge className="border-primary/30 bg-primary/10 text-primary" variant="outline">
          <Settings aria-hidden="true" className="size-3.5" />
          Inställningar
        </Badge>
        <h1>Inställningar</h1>
        <p className="page-lede">Utseende och information om QiNora.</p>
      </header>

      <Card className="data-card">
        <CardHeader>
          <CardDescription>Tema</CardDescription>
          <CardTitle>Utseende</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Button
            onClick={() => setTheme("light")}
            type="button"
            variant={theme === "light" ? "default" : "secondary"}
          >
            <Sun aria-hidden="true" />
            Ljust läge
          </Button>
          <Button
            onClick={() => setTheme("dark")}
            type="button"
            variant={theme === "dark" ? "default" : "secondary"}
          >
            <Moon aria-hidden="true" />
            Mörkt läge
          </Button>
        </CardContent>
      </Card>

      <Card className="data-card">
        <CardHeader>
          <CardDescription>Version</CardDescription>
          <CardTitle>Om QiNora</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-1.5 text-sm">
          <div>
            <span className="text-muted-foreground">Version </span>
            <span className="font-mono">{APP_VERSION}</span>
          </div>
          <p className="text-muted-foreground">
            QiNora TMS — AI-driven speditionsplattform för förfrågningar, offerter, sändningar
            och fakturagranskning.
          </p>
        </CardContent>
      </Card>
    </section>
  );
}
