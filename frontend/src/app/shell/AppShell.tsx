import { Activity, Inbox, Settings, Truck } from "lucide-react";
import { Outlet } from "react-router-dom";

import { Button } from "@/components/ui/button";

const navItems = [
  { label: "Tower", icon: Activity },
  { label: "Inbox", icon: Inbox },
  { label: "Shipments", icon: Truck },
  { label: "Admin", icon: Settings },
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
              className="nav-item"
              key={item.label}
              type="button"
              title={item.label}
              variant="ghost"
            >
              <item.icon aria-hidden="true" size={18} />
              <span>{item.label}</span>
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
