import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";

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
      <form className="login-card" onSubmit={handleSubmit}>
        <div className="brand">
          <span className="brand-mark">Q</span>
          <span>QiNora</span>
        </div>
        <p className="muted">Ange lösenordet för att fortsätta.</p>
        <input
          autoComplete="current-password"
          autoFocus
          aria-label="Password"
          onChange={(event) => setPassword(event.target.value)}
          placeholder="Lösenord"
          type="password"
          value={password}
        />
        {error ? <p className="login-error">{error}</p> : null}
        <Button disabled={isSubmitting || password.trim().length === 0} type="submit">
          {isSubmitting ? "Loggar in..." : "Logga in"}
        </Button>
      </form>
    </div>
  );
}
