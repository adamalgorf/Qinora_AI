import { Activity, FileText, Inbox, RadioTower, Settings, Truck, Users } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

import { Button } from "@/components/ui/button";

const navItems = [
  { label: "Tower", href: "/", icon: Activity },
  { label: "Inbox", href: "/inbox", icon: Inbox },
  { label: "Requests", href: "/requests", icon: RadioTower },
  { label: "Quotes", href: "/quotes", icon: FileText },
  { label: "Shipments", href: "/shipments", icon: Truck },
  { label: "Carriers", href: "/carriers", icon: Users },
  { label: "Admin", href: "/admin", icon: Settings },
];

export function AppShell() {
  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand">
          <span className="brand-mark">Q</span>
          <span>QiNora</span>
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
