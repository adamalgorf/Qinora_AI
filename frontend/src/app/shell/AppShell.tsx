import {
  Activity,
  ContactRound,
  FileCheck2,
  FileText,
  Inbox,
  RadioTower,
  Search,
  Settings,
  Truck,
  Users,
} from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import {
  apiGet,
  apiPost,
  clearAuthToken,
  getAuthToken,
  setAuthToken,
  type AuthConfig,
  type AuthMe,
  type DevTokenPayload,
  type LoginPayload,
  type SearchResultItem,
  type TokenResponse,
} from "@/shared/api/client";
import { LoginScreen } from "./LoginScreen";

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
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState("");
  const normalizedSearchTerm = searchTerm.trim();

  const configQuery = useQuery({
    queryKey: ["auth-config"],
    queryFn: () => apiGet<AuthConfig>("/auth/config"),
  });
  const loginRequired = configQuery.data?.login_required ?? false;

  const authQuery = useQuery({
    queryKey: ["auth-me", loginRequired],
    enabled: configQuery.isSuccess,
    queryFn: async () => {
      if (loginRequired) {
        if (!getAuthToken()) {
          return null;
        }
        try {
          return await apiGet<AuthMe>("/auth/me");
        } catch (error) {
          if (isUnauthorized(error)) {
            clearAuthToken();
            return null;
          }
          throw error;
        }
      }

      const currentUser = await getCurrentUser();
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

  const loginMutation = useMutation({
    mutationFn: (password: string) =>
      apiPost<TokenResponse, LoginPayload>("/auth/login", { password }),
    onSuccess: (session) => {
      setAuthToken(session.access_token);
      queryClient.setQueryData(["auth-me", true], session.user);
    },
  });

  const searchQuery = useQuery({
    queryKey: ["global-search", normalizedSearchTerm],
    queryFn: () =>
      apiGet<SearchResultItem[]>(`/search?q=${encodeURIComponent(normalizedSearchTerm)}`),
    enabled: normalizedSearchTerm.length >= 2,
  });

  useEffect(() => {
    function focusGlobalSearch(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        document.getElementById("global-search")?.focus();
      }
    }

    window.addEventListener("keydown", focusGlobalSearch);
    return () => window.removeEventListener("keydown", focusGlobalSearch);
  }, []);

  function selectSearchResult(result: SearchResultItem) {
    navigate(result.href);
    setSearchTerm("");
  }

  if (configQuery.isLoading || authQuery.isLoading) {
    return null;
  }

  if (loginRequired && !authQuery.data) {
    return (
      <LoginScreen
        error={loginMutation.isError ? "Fel lösenord." : null}
        isSubmitting={loginMutation.isPending}
        onSubmit={(password) => loginMutation.mutate(password)}
      />
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand">
          <span className="brand-mark">Q</span>
          <span>QiNora</span>
        </div>
        <div className="global-search">
          <Search aria-hidden="true" size={16} />
          <input
            id="global-search"
            aria-label="Search QiNora"
            autoComplete="off"
            placeholder="Search QiNora"
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
          />
          <kbd>Ctrl K</kbd>
        </div>
        {normalizedSearchTerm.length >= 2 ? (
          <div className="search-results" role="listbox" aria-label="Search results">
            {searchQuery.isLoading ? <p className="muted">Searching...</p> : null}
            {(searchQuery.data ?? []).map((result) => (
              <button
                key={`${result.entity_type}-${result.id}`}
                type="button"
                role="option"
                onClick={() => selectSearchResult(result)}
              >
                <span>{result.entity_type}</span>
                <strong>{result.label}</strong>
                <small>{result.description}</small>
              </button>
            ))}
            {!searchQuery.isLoading && (searchQuery.data ?? []).length === 0 ? (
              <p className="muted">No matches.</p>
            ) : null}
          </div>
        ) : null}
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

async function getCurrentUser(): Promise<AuthMe> {
  try {
    return await apiGet<AuthMe>("/auth/me");
  } catch (error) {
    if (getAuthToken() && isUnauthorized(error)) {
      clearAuthToken();
      return apiGet<AuthMe>("/auth/me");
    }
    throw error;
  }
}

function isUnauthorized(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "status" in error &&
    (error as { status?: number }).status === 401
  );
}
