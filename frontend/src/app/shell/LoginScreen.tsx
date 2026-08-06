import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Logo } from "./Logo";

type LoginScreenProps = {
  error: string | null;
  isSubmitting: boolean;
  onSubmit: (password: string) => void;
};

export function LoginScreen({ error, isSubmitting, onSubmit }: LoginScreenProps) {
  const [password, setPassword] = useState("");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (password.trim().length > 0) {
      onSubmit(password);
    }
  }

  return (
    <div className="login-screen">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <div className="brand">
            <span className="brand-mark">
              <Logo />
            </span>
            <span>QiNora</span>
          </div>
          <CardTitle>Välkommen tillbaka</CardTitle>
          <CardDescription>Ange lösenordet för att fortsätta.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="grid gap-4" onSubmit={handleSubmit}>
            <div className="grid gap-2">
              <Label htmlFor="login-password">Lösenord</Label>
              <Input
                autoComplete="current-password"
                autoFocus
                id="login-password"
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Lösenord"
                type="password"
                value={password}
              />
            </div>
            {error ? <p className="text-sm text-destructive">{error}</p> : null}
            <Button
              className="w-full"
              disabled={isSubmitting || password.trim().length === 0}
              type="submit"
            >
              {isSubmitting ? "Loggar in..." : "Logga in"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
