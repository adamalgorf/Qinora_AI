import { KeyRound, Mail, Sparkles, Truck } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { getLastLoginEmail, setLastLoginEmail } from "@/shared/api/client";

type LoginScreenProps = {
  error: string | null;
  isSubmitting: boolean;
  onSubmit: (email: string, password: string, rememberMe: boolean) => void;
};

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function LoginScreen({ error, isSubmitting, onSubmit }: LoginScreenProps) {
  const [mode, setMode] = useState<"password" | "magic">("password");
  const [email, setEmail] = useState(getLastLoginEmail);
  const [password, setPassword] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  const emailValid = EMAIL_PATTERN.test(email.trim());
  const canSubmit = emailValid && password.trim().length > 0 && !isSubmitting;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    setLastLoginEmail(email.trim());
    onSubmit(email.trim(), password, true);
  }

  function selectMagicLink() {
    setMode("magic");
    setNotice("Magic Link är inte tillgängligt ännu. Logga in med lösenord istället.");
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-6 py-12">
      <Card className="w-full max-w-md">
        <CardContent className="flex flex-col gap-6 p-8">
          <div className="flex flex-col items-center gap-3 text-center">
            <span className="flex size-14 items-center justify-center rounded-2xl bg-blue-600 text-white shadow-lg shadow-blue-600/30">
              <Truck aria-hidden="true" className="size-7" />
            </span>
            <div>
              <h1 className="text-2xl font-bold text-foreground">QiNoraTMS</h1>
              <p className="text-sm text-muted-foreground">Logga in på ditt konto</p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-1 rounded-lg bg-muted p-1">
            <button
              className={cn(
                "flex items-center justify-center gap-1.5 rounded-md py-2 text-sm font-medium transition-colors",
                mode === "password"
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
              onClick={() => setMode("password")}
              type="button"
            >
              <KeyRound aria-hidden="true" className="size-4" />
              Lösenord
            </button>
            <button
              className={cn(
                "flex items-center justify-center gap-1.5 rounded-md py-2 text-sm font-medium transition-colors",
                mode === "magic"
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
              onClick={selectMagicLink}
              type="button"
            >
              <Sparkles aria-hidden="true" className="size-4" />
              Magic Link
            </button>
          </div>

          <form className="grid gap-4" onSubmit={handleSubmit}>
            <div className="grid gap-1.5">
              <Label htmlFor="login-email">E-post</Label>
              <div className="relative">
                <Mail
                  aria-hidden="true"
                  className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                />
                <Input
                  autoComplete="username"
                  autoFocus
                  className="pl-9"
                  id="login-email"
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="din@email.com"
                  type="email"
                  value={email}
                />
              </div>
            </div>

            <div className="grid gap-1.5">
              <Label htmlFor="login-password">Lösenord</Label>
              <Input
                autoComplete="current-password"
                id="login-password"
                onChange={(event) => setPassword(event.target.value)}
                placeholder="••••••••"
                type="password"
                value={password}
              />
              <div className="flex justify-end">
                <button
                  className="text-sm font-medium text-blue-600 hover:underline"
                  onClick={() =>
                    setNotice("Återställning av lösenord är inte tillgängligt ännu. Kontakta din administratör.")
                  }
                  type="button"
                >
                  Glömt lösenord?
                </button>
              </div>
            </div>

            {error ? <p className="text-sm text-destructive">{error}</p> : null}

            <Button
              className="w-full bg-blue-600 text-white hover:bg-blue-700"
              disabled={!canSubmit}
              type="submit"
            >
              {isSubmitting ? "Loggar in…" : "Logga in"}
            </Button>
          </form>

          <p className="text-center text-sm text-muted-foreground">
            Har du inget konto?{" "}
            <button
              className="font-medium text-blue-600 hover:underline"
              onClick={() =>
                setNotice("Nya konton skapas av din administratör under Inställningar → Användare.")
              }
              type="button"
            >
              Skapa konto
            </button>
          </p>
        </CardContent>
      </Card>

      <Dialog open={Boolean(notice)} onOpenChange={() => setNotice(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Inte tillgängligt ännu</DialogTitle>
            <DialogDescription>{notice}</DialogDescription>
          </DialogHeader>
        </DialogContent>
      </Dialog>
    </div>
  );
}
