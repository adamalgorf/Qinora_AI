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
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
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
import { ThemeToggle } from "@/shared/theme/ThemeToggle";
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
  const location = useLocation();
  const queryClient = useQueryClient();
  const [searchOpen, setSearchOpen] = useState(false);
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
    function toggleSearch(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSearchOpen((open) => !open);
      }
    }

    window.addEventListener("keydown", toggleSearch);
    return () => window.removeEventListener("keydown", toggleSearch);
  }, []);

  function selectSearchResult(result: SearchResultItem) {
    navigate(result.href);
    setSearchTerm("");
    setSearchOpen(false);
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

  const searchResults = searchQuery.data ?? [];

  return (
    <SidebarProvider>
      <Sidebar collapsible="icon">
        <SidebarHeader>
          <div className="brand">
            <span className="brand-mark">Q</span>
            <span className="group-data-[collapsible=icon]:hidden">QiNora</span>
          </div>
        </SidebarHeader>
        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupContent>
              <SidebarMenu>
                {navItems.map((item) => (
                  <SidebarMenuItem key={item.label}>
                    <SidebarMenuButton
                      asChild
                      isActive={location.pathname === item.href}
                      tooltip={item.label}
                    >
                      <NavLink to={item.href}>
                        <item.icon aria-hidden="true" />
                        <span>{item.label}</span>
                      </NavLink>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
      </Sidebar>
      <SidebarInset>
        <header className="app-header">
          <SidebarTrigger />
          <Button
            aria-label="Search QiNora"
            className="search-trigger"
            onClick={() => setSearchOpen(true)}
            variant="outline"
          >
            <Search aria-hidden="true" size={16} />
            <span className="hidden sm:inline">Search QiNora</span>
            <kbd className="hidden sm:inline-flex">Ctrl K</kbd>
          </Button>
          <div className="app-header-actions">
            <ThemeToggle />
          </div>
        </header>
        <main className="main-surface">
          <Outlet />
        </main>
      </SidebarInset>
      <Dialog onOpenChange={setSearchOpen} open={searchOpen}>
        <DialogContent className="overflow-hidden p-0">
          <Command shouldFilter={false}>
            <CommandInput
              onValueChange={setSearchTerm}
              placeholder="Search QiNora"
              value={searchTerm}
            />
            <CommandList>
              {searchQuery.isLoading ? (
                <div className="px-3 py-6 text-center text-sm text-muted-foreground">
                  Searching...
                </div>
              ) : null}
              {!searchQuery.isLoading && normalizedSearchTerm.length >= 2 ? (
                <CommandEmpty>No matches.</CommandEmpty>
              ) : null}
              {searchResults.length > 0 ? (
                <CommandGroup heading="Results">
                  {searchResults.map((result) => (
                    <CommandItem
                      key={`${result.entity_type}-${result.id}`}
                      onSelect={() => selectSearchResult(result)}
                      value={`${result.entity_type}-${result.id}`}
                    >
                      <div className="flex flex-col gap-0.5">
                        <span className="text-xs uppercase tracking-wide text-muted-foreground">
                          {result.entity_type}
                        </span>
                        <span className="font-medium">{result.label}</span>
                        <span className="text-xs text-muted-foreground">
                          {result.description}
                        </span>
                      </div>
                    </CommandItem>
                  ))}
                </CommandGroup>
              ) : null}
            </CommandList>
          </Command>
        </DialogContent>
      </Dialog>
    </SidebarProvider>
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
