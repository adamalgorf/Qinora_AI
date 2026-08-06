import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider, createBrowserRouter } from "react-router-dom";

import { ThemeProvider } from "@/shared/theme/ThemeProvider";

import { AppShell } from "./shell/AppShell";
import { ControlTowerPage } from "../features/control-tower/ControlTowerPage";
import { AdminPage } from "../features/modules/AdminPage";
import { CarriersPage } from "../features/modules/CarriersPage";
import { ContactsPage } from "../features/modules/ContactsPage";
import { InboxPage } from "../features/modules/InboxPage";
import { InvoicesPage } from "../features/modules/InvoicesPage";
import { QuotesPage } from "../features/modules/QuotesPage";
import { RequestsPage } from "../features/modules/RequestsPage";
import { ShipmentsPage } from "../features/modules/ShipmentsPage";
import { SettingsPage } from "../features/settings/SettingsPage";
import "./styles.css";

const queryClient = new QueryClient();
const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <ControlTowerPage /> },
      { path: "inbox", element: <InboxPage /> },
      { path: "requests", element: <RequestsPage /> },
      { path: "contacts", element: <ContactsPage /> },
      { path: "quotes", element: <QuotesPage /> },
      { path: "shipments", element: <ShipmentsPage /> },
      { path: "invoices", element: <InvoicesPage /> },
      { path: "carriers", element: <CarriersPage /> },
      { path: "admin", element: <AdminPage /> },
      { path: "settings", element: <SettingsPage /> },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
);
