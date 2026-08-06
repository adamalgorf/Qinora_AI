import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

export function LoadingScreen() {
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setSlow(true), 3000);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <div className="login-screen">
      <div className="flex flex-col items-center gap-4 text-center">
        <span className="brand-mark">Q</span>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 aria-hidden="true" className="size-4 animate-spin" />
          Loading QiNora...
        </div>
        {slow ? (
          <p className="max-w-xs text-xs text-muted-foreground">
            The free-tier server can take up to a minute to wake up after being idle. Almost
            there.
          </p>
        ) : null}
      </div>
    </div>
  );
}
