import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider, createBrowserRouter } from "react-router-dom";

import { ThemeProvider } from "@/shared/theme/ThemeProvider";

import { AppShell } from "./shell/AppShell";
import { AnalyticsPage } from "../features/analytics/AnalyticsPage";
import { AutomationsPage } from "../features/automations/AutomationsPage";
import { CaseDetailPage } from "../features/cases/CaseDetailPage";
import { CasesPage } from "../features/cases/CasesPage";
import { CustomerCasesPage } from "../features/customers/CustomerCasesPage";
import { CustomersPage } from "../features/customers/CustomersPage";
import { DocumentsPage } from "../features/documents/DocumentsPage";
import { InboxPage } from "../features/inbox/InboxPage";
import { OverviewPage } from "../features/overview/OverviewPage";
import { QuotesPage } from "../features/quotes/QuotesPage";
import { CarriersPage } from "../features/modules/CarriersPage";
import { SettingsPage } from "../features/settings/SettingsPage";
import "./styles.css";

const queryClient = new QueryClient();
const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <OverviewPage /> },
      { path: "inbox", element: <InboxPage /> },
      { path: "cases", element: <CasesPage /> },
      { path: "cases/:id", element: <CaseDetailPage /> },
      { path: "quotes", element: <QuotesPage /> },
      { path: "automations", element: <AutomationsPage /> },
      { path: "documents", element: <DocumentsPage /> },
      { path: "customers", element: <CustomersPage /> },
      { path: "customers/by-email/:email", element: <CustomerCasesPage /> },
      { path: "analytics", element: <AnalyticsPage /> },
      { path: "carriers", element: <CarriersPage /> },
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
