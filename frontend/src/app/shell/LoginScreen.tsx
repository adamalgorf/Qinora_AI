import { Eye, EyeOff, KeyRound, Lock, Mail } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getLastLoginEmail, setLastLoginEmail } from "@/shared/api/client";
import { Logo } from "./Logo";

type LoginScreenProps = {
  error: string | null;
  isSubmitting: boolean;
  onSubmit: (password: string, rememberMe: boolean) => void;
};

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function LoginScreen({ error, isSubmitting, onSubmit }: LoginScreenProps) {
  const [email, setEmail] = useState(getLastLoginEmail);
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);

  const emailValid = EMAIL_PATTERN.test(email.trim());
  const canSubmit = emailValid && password.trim().length > 0 && !isSubmitting;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    setLastLoginEmail(email.trim());
    onSubmit(password, rememberMe);
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-background px-6 py-12">
      <div className="flex flex-col items-center gap-1">
        <div className="flex items-center gap-2.5">
          <span className="flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-[0_8px_20px_hsl(var(--primary)/0.2)]">
            <Logo size={20} />
          </span>
          <span className="text-xl font-bold text-foreground">Qinora</span>
        </div>
        <p className="text-sm text-muted-foreground">Din AI-drivna logistikchef</p>
      </div>

      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-xl">Logga in i kommandocenter</CardTitle>
          <CardDescription>Vänligen ange dina företagsuppgifter för att fortsätta.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="grid gap-4" onSubmit={handleSubmit}>
            <div className="grid gap-1.5">
              <Label htmlFor="login-email">E-postadress</Label>
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
                  placeholder="namn@foretag.se"
                  type="email"
                  value={email}
                />
              </div>
            </div>

            <div className="grid gap-1.5">
              <Label htmlFor="login-password">Lösenord</Label>
              <div className="relative">
                <Lock
                  aria-hidden="true"
                  className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                />
                <Input
                  autoComplete="current-password"
                  className="pl-9 pr-9"
                  id="login-password"
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="Lösenord"
                  type={showPassword ? "text" : "password"}
                  value={password}
                />
                <button
                  aria-label={showPassword ? "Dölj lösenord" : "Visa lösenord"}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  onClick={() => setShowPassword((v) => !v)}
                  type="button"
                >
                  {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
            </div>

            <div className="flex items-center justify-between text-sm">
              <label className="flex items-center gap-2 text-muted-foreground">
                <input
                  checked={rememberMe}
                  className="size-4 rounded border-border accent-primary"
                  onChange={(event) => setRememberMe(event.target.checked)}
                  type="checkbox"
                />
                Kom ihåg mig på denna enhet
              </label>
              <button
                className="font-medium text-primary hover:underline"
                onClick={() => setNotice("Återställning av lösenord är inte tillgängligt ännu. Kontakta IT-supporten.")}
                type="button"
              >
                Glömt lösenordet?
              </button>
            </div>

            {error ? <p className="text-sm text-destructive">{error}</p> : null}

            <Button className="w-full" disabled={!canSubmit} type="submit">
              {isSubmitting ? "Loggar in…" : "Logga in"}
            </Button>

            <div className="relative py-1 text-center">
              <span className="relative z-10 bg-card px-3 text-xs font-medium text-muted-foreground">
                ELLER
              </span>
              <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-border" />
            </div>

            <Button
              className="w-full"
              type="button"
              variant="outline"
              onClick={() => setNotice("Enterprise SSO är inte konfigurerat för det här kontot ännu.")}
            >
              <KeyRound aria-hidden="true" className="size-4" />
              Logga in med Volvo Enterprise SSO
            </Button>
          </form>
        </CardContent>
      </Card>

      <p className="text-sm text-muted-foreground">
        Behöver du behörighet eller administrativt stöd?{" "}
        <a className="font-medium text-primary hover:underline" href="mailto:it-support@qinora.se">
          Kontakta IT-supporten
        </a>
      </p>

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
