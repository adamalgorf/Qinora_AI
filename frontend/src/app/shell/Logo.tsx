import { Route } from "lucide-react";

/** The QiNora mark: a routed path between two nodes, inside the brand-mark box. */
export function Logo({ size = 18 }: { size?: number }) {
  return <Route aria-hidden="true" size={size} strokeWidth={2.25} />;
}
