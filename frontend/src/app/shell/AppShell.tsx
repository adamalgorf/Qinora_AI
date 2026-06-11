import {
  Activity,
  ContactRound,
  FileCheck2,
  FileText,
  Inbox,
  RadioTower,
  Settings,
  Truck,
  Users,
} from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  apiGet,
  apiPost,
  getAuthToken,
  setAuthToken,
  type AuthMe,
  type DevTokenPayload,
  type TokenResponse,
} from "@/shared/api/client";

const navItems = [
  { label: "Tower", href: "/", icon: Activity },
  { label: "Inbox", href: "/inbox", icon: Inbox },
  { label: "Requests", href: "/requests", icon: RadioTower },
  { label: "Contacts", href: "/contacts", icon: ContactRound },
  { label: "Quotes", href: "/quotes", icon: FileText },
  { label: "Shipments", href: "/shipments", icon: Truck },
  { label: "Invoices", href: "/invoices", icon: FileCheck2 },
  { label: "Carriers", href: "/carriers", icon: Users },
  { label: "Admin", href: "/admin", icon: Settings },
];

export function AppShell() {
  const authQuery = useQuery({
    queryKey: ["auth-me"],
    queryFn: async () => {
      const currentUser = await apiGet<AuthMe>("/auth/me");
      if (getAuthToken()) {
        return currentUser;
      }

      const session = await apiPost<TokenResponse, DevTokenPayload>("/auth/dev-token", {
        user_id: currentUser.user_id,
        tenant_id: currentUser.tenant_id,
        roles: currentUser.roles,
      });
      setAuthToken(session.access_token);
      return session.user;
    },
  });

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand">
          <span className="brand-mark">Q</span>
          <span>QiNora</span>
        </div>
        <div className="session-chip">
          <span>{authQuery.data?.tenant_id ?? "dev-tenant"}</span>
          <Badge variant="secondary">{authQuery.data?.roles[0] ?? "admin"}</Badge>
        </div>
        <nav className="nav-list">
          {navItems.map((item) => (
            <Button
              asChild
              className="nav-item"
              key={item.label}
              title={item.label}
              variant="ghost"
            >
              <NavLink to={item.href}>
                <item.icon aria-hidden="true" size={18} />
                <span>{item.label}</span>
              </NavLink>
            </Button>
          ))}
        </nav>
      </aside>
      <main className="main-surface">
        <Outlet />
      </main>
    </div>
  );
}
