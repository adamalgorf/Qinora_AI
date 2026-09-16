import {
  BarChart3,
  FileCheck2,
  FileText,
  FolderArchive,
  LayoutDashboard,
  LogOut,
  Mail,
  Search,
  Settings,
  Users,
  Workflow,
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
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
  type InboxListItem,
  type LoginPayload,
  type SearchResultItem,
  type TokenResponse,
} from "@/shared/api/client";
import { ThemeToggle } from "@/shared/theme/ThemeToggle";
import { APP_VERSION } from "@/shared/version";
import { LoadingScreen } from "./LoadingScreen";
import { LoginScreen } from "./LoginScreen";

const navItems = [
  { label: "Översikt", href: "/", icon: LayoutDashboard },
  { label: "Inkorg", href: "/inbox", icon: Mail },
  { label: "Ärenden", href: "/cases", icon: FolderArchive },
  { label: "Offerter", href: "/quotes", icon: FileCheck2 },
  { label: "Automatiseringar", href: "/automations", icon: Workflow },
  { label: "Dokument", href: "/documents", icon: FileText },
  { label: "Kunder", href: "/customers", icon: Users },
  { label: "Analys", href: "/analytics", icon: BarChart3 },
];

function isNavItemActive(pathname: string, href: string): boolean {
  if (href === "/") {
    return pathname === "/";
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [logoutConfirmOpen, setLogoutConfirmOpen] = useState(false);
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
    mutationFn: ({ email, password }: { email: string; password: string; rememberMe: boolean }) =>
      apiPost<TokenResponse, LoginPayload>("/auth/login", { email, password }),
    onSuccess: (session, variables) => {
      setAuthToken(session.access_token, variables.rememberMe);
      queryClient.setQueryData(["auth-me", true], session.user);
    },
  });

  const searchQuery = useQuery({
    queryKey: ["global-search", normalizedSearchTerm],
    queryFn: () =>
      apiGet<SearchResultItem[]>(`/search?q=${encodeURIComponent(normalizedSearchTerm)}`),
    enabled: normalizedSearchTerm.length >= 2,
  });

  const inboxQuery = useQuery({
    queryKey: ["inbox"],
    queryFn: () => apiGet<InboxListItem[]>("/inbox/pending"),
    enabled: Boolean(authQuery.data),
  });
  const unreadInboxCount = inboxQuery.data?.length ?? 0;

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

  function confirmLogout() {
    clearAuthToken();
    queryClient.setQueryData(["auth-me", loginRequired], null);
    void queryClient.invalidateQueries({ queryKey: ["auth-me"] });
    setLogoutConfirmOpen(false);
    navigate("/");
  }

  if (configQuery.isLoading || authQuery.isLoading) {
    return <LoadingScreen />;
  }

  if (loginRequired && !authQuery.data) {
    return (
      <LoginScreen
        error={loginMutation.isError ? "Fel e-post eller lösenord." : null}
        isSubmitting={loginMutation.isPending}
        onSubmit={(email, password, rememberMe) =>
          loginMutation.mutate({ email, password, rememberMe })
        }
      />
    );
  }

  const searchResults = searchQuery.data ?? [];

  const displayName = authQuery.data?.full_name || "Qinora User";
  const displayRole = authQuery.data?.roles?.[0] ?? "Operatör";
  const initials = displayName
    .split(/[\s._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");

  return (
    <SidebarProvider style={{ "--sidebar-width": "240px" } as React.CSSProperties}>
      <Sidebar collapsible="icon">
        <SidebarHeader className="gap-8 px-4 py-6">
          <div className="flex flex-col gap-1 group-data-[collapsible=icon]:hidden">
            <span className="text-[20px] font-bold leading-none text-white">Qinora</span>
            <span className="text-[11px] text-sidebar-foreground/70">
              Din AI-drivna logistikchef
            </span>
          </div>
        </SidebarHeader>
        <SidebarContent className="px-2">
          <SidebarGroup className="p-0">
            <SidebarGroupContent>
              <SidebarMenu className="gap-1">
                {navItems.map((item) => (
                  <SidebarMenuItem key={item.label}>
                    <SidebarMenuButton
                      asChild
                      className="h-auto rounded-md px-3 py-2.5 text-[14px] data-[active=true]:font-semibold"
                      isActive={isNavItemActive(location.pathname, item.href)}
                      tooltip={item.label}
                    >
                      <NavLink to={item.href}>
                        <item.icon aria-hidden="true" className="size-4" />
                        <span>{item.label}</span>
                        {item.href === "/inbox" && unreadInboxCount > 0 ? (
                          <span className="ml-auto flex min-w-[18px] items-center justify-center rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-semibold text-primary-foreground">
                            {unreadInboxCount}
                          </span>
                        ) : null}
                      </NavLink>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
        <SidebarFooter className="gap-4 px-4 pb-6">
          <div className="h-px bg-sidebar-border group-data-[collapsible=icon]:hidden" />
          <div className="flex items-center gap-3 group-data-[collapsible=icon]:hidden">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-sidebar-accent text-[12px] font-semibold text-white">
              {initials || "Q"}
            </span>
            <div className="flex min-w-0 flex-col gap-0.5">
              <span className="truncate text-[13px] font-semibold text-white">{displayName}</span>
              <span className="truncate text-[11px] text-sidebar-foreground/70">{displayRole}</span>
            </div>
          </div>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton
                asChild
                className="h-auto rounded-md px-3 py-2.5 text-[14px]"
                isActive={location.pathname === "/settings"}
                tooltip="Inställningar"
              >
                <NavLink to="/settings">
                  <Settings aria-hidden="true" className="size-4" />
                  <span>Inställningar</span>
                </NavLink>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton
                className="h-auto rounded-md px-3 py-2.5 text-[14px] text-sidebar-foreground hover:text-destructive"
                tooltip="Logga ut"
                onClick={() => setLogoutConfirmOpen(true)}
              >
                <LogOut aria-hidden="true" className="size-4" />
                <span>Logga ut</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
          <div className="px-2 pb-1 text-xs text-sidebar-foreground/50 group-data-[collapsible=icon]:hidden">
            QiNora v{APP_VERSION}
          </div>
        </SidebarFooter>
      </Sidebar>
      <SidebarInset className="min-w-0">
        <header className="app-header">
          <SidebarTrigger />
          <Button
            aria-label="Sök i QiNora"
            className="search-trigger rounded-full shadow-none"
            onClick={() => setSearchOpen(true)}
            variant="secondary"
          >
            <Search aria-hidden="true" className="sm:hidden" size={16} />
            <span className="hidden sm:inline">Sök</span>
            <kbd className="hidden sm:inline-flex">⌘K</kbd>
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
              placeholder="Sök i QiNora"
              value={searchTerm}
            />
            <CommandList>
              {searchQuery.isLoading ? (
                <div className="px-3 py-6 text-center text-sm text-muted-foreground">
                  Söker…
                </div>
              ) : null}
              {!searchQuery.isLoading && normalizedSearchTerm.length >= 2 ? (
                <CommandEmpty>Inga träffar.</CommandEmpty>
              ) : null}
              {searchResults.length > 0 ? (
                <CommandGroup heading="Resultat">
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
      <Dialog onOpenChange={setLogoutConfirmOpen} open={logoutConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Logga ut?</DialogTitle>
            <DialogDescription>
              Du loggas ut från QiNora på den här enheten. Eventuella osparade ändringar går
              förlorade.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setLogoutConfirmOpen(false)}>
              Avbryt
            </Button>
            <Button variant="destructive" onClick={confirmLogout}>
              <LogOut aria-hidden="true" className="size-4" />
              Logga ut
            </Button>
          </DialogFooter>
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
