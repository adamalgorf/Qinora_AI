import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import { Logo } from "./Logo";

export function LoadingScreen() {
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setSlow(true), 3000);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <div className="login-screen">
      <div className="flex flex-col items-center gap-4 text-center">
        <span className="brand-mark">
          <Logo />
        </span>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 aria-hidden="true" className="size-4 animate-spin" />
          Laddar QiNora…
        </div>
        {slow ? (
          <p className="max-w-xs text-xs text-muted-foreground">
            Servern kan ta upp till en minut att vakna efter att ha varit inaktiv. Snart klart.
          </p>
        ) : null}
      </div>
    </div>
  );
}
