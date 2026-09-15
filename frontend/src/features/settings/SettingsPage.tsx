import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { PageShell } from "@/components/patterns/PageShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useTheme } from "@/shared/theme/ThemeProvider";
import { apiGet, type AuthMe, type CaseListItem, type QuoteListItem } from "@/shared/api/client";
import { APP_VERSION } from "@/shared/version";

type ProfileForm = {
  firstName: string;
  lastName: string;
  email: string;
  phone: string;
  timezone: string;
};

const EMPTY_PROFILE: ProfileForm = {
  firstName: "",
  lastName: "",
  email: "",
  phone: "",
  timezone: "Europe/Stockholm (GMT+01:00)",
};

const PROFILE_STORAGE_KEY = "qinora-profile";

function loadStoredProfile(): ProfileForm {
  try {
    const raw = window.localStorage.getItem(PROFILE_STORAGE_KEY);
    if (!raw) return EMPTY_PROFILE;
    return { ...EMPTY_PROFILE, ...(JSON.parse(raw) as Partial<ProfileForm>) };
  } catch {
    return EMPTY_PROFILE;
  }
}

const TIMEZONES = [
  "Europe/Stockholm (GMT+01:00)",
  "Europe/London (GMT+00:00)",
  "Europe/Berlin (GMT+01:00)",
  "America/New_York (GMT-05:00)",
];

export function SettingsPage() {
  const { theme, setTheme } = useTheme();
  const [form, setForm] = useState<ProfileForm>(loadStoredProfile);
  const [savedNotice, setSavedNotice] = useState(false);
  const [unavailableNotice, setUnavailableNotice] = useState<string | null>(null);

  const authQuery = useQuery({
    queryKey: ["auth-me-settings"],
    queryFn: () => apiGet<AuthMe>("/auth/me"),
  });
  const casesQuery = useQuery({
    queryKey: ["cases"],
    queryFn: () => apiGet<CaseListItem[]>("/cases"),
  });
  const quotesQuery = useQuery({
    queryKey: ["quotes"],
    queryFn: () => apiGet<QuoteListItem[]>("/quotes"),
  });

  useEffect(() => {
    if (!savedNotice) return;
    const timer = window.setTimeout(() => setSavedNotice(false), 3000);
    return () => window.clearTimeout(timer);
  }, [savedNotice]);

  const role = authQuery.data?.roles?.[0] ?? "—";
  const quotes = quotesQuery.data ?? [];
  const acceptedRate = quotes.length
    ? Math.round(
        (quotes.filter((q) => q.status === "accepted" || q.status === "converted").length /
          quotes.length) *
          100,
      )
    : null;
  const initials =
    [form.firstName, form.lastName]
      .filter(Boolean)
      .map((part) => part[0]?.toUpperCase())
      .join("") || (authQuery.data?.user_id?.slice(0, 2).toUpperCase() ?? "Q");

  function updateField<K extends keyof ProfileForm>(field: K, value: ProfileForm[K]) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function saveProfile() {
    window.localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(form));
    setSavedNotice(true);
  }

  function cancelChanges() {
    setForm(loadStoredProfile());
  }

  return (
    <PageShell subtitle="Min Profil & Kontoinställningar" title="Inställningar">
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
        <div className="flex flex-col gap-6">
          <Card>
            <CardContent className="flex flex-col items-center gap-5 p-6">
              <div className="flex flex-col items-center gap-3">
                <span className="flex size-24 items-center justify-center rounded-full bg-sidebar text-2xl font-semibold text-white">
                  {initials}
                </span>
                <div className="flex gap-2">
                  <Button
                    className="h-auto bg-accent/10 px-3 py-1.5 text-xs text-accent hover:bg-accent/20"
                    size="sm"
                    variant="ghost"
                    onClick={() => setUnavailableNotice("Uppladdning av profilbild är inte tillgängligt ännu.")}
                  >
                    Ladda upp ny
                  </Button>
                  <Button
                    className="h-auto bg-destructive/10 px-3 py-1.5 text-xs text-destructive hover:bg-destructive/20"
                    size="sm"
                    variant="ghost"
                    onClick={() => setUnavailableNotice("Borttagning av profilbild är inte tillgängligt ännu.")}
                  >
                    Ta bort
                  </Button>
                </div>
              </div>
              <div className="h-px w-full bg-border" />
              <div className="flex w-full flex-col gap-3">
                <div>
                  <p className="text-[11px] font-semibold uppercase text-muted-foreground">Roll</p>
                  <p className="text-sm text-foreground">{role}</p>
                </div>
                <div>
                  <p className="text-[11px] font-semibold uppercase text-muted-foreground">
                    Konto-ID
                  </p>
                  <p className="truncate text-sm text-foreground">
                    {authQuery.data?.user_id ?? "—"}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="flex flex-col gap-3 p-5">
              <p className="text-sm font-semibold text-foreground">Operativ Aktivitet</p>
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Hanterade ärenden</span>
                <span className="font-bold text-foreground">
                  {casesQuery.isLoading ? "…" : `${casesQuery.data?.length ?? 0} st`}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Godkända offerter</span>
                <span className="font-bold text-foreground">
                  {quotesQuery.isLoading ? "…" : acceptedRate !== null ? `${acceptedRate}%` : "—"}
                </span>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="flex flex-col gap-2 p-5 text-sm">
              <p className="font-semibold text-foreground">Om QiNora</p>
              <p className="text-muted-foreground">
                Version <span className="font-mono">{APP_VERSION}</span>
              </p>
            </CardContent>
          </Card>
        </div>

        <div className="flex flex-col gap-6">
          <Card>
            <CardContent className="flex flex-col gap-5 p-6">
              <div>
                <h2 className="text-base font-semibold">Personuppgifter & Kontakt</h2>
                <p className="text-xs text-muted-foreground">
                  Uppdatera dina grundläggande kontouppgifter och hur vi kan nå dig.
                </p>
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="grid gap-1.5">
                  <Label htmlFor="profile-first-name">Förnamn</Label>
                  <Input
                    id="profile-first-name"
                    value={form.firstName}
                    onChange={(e) => updateField("firstName", e.target.value)}
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor="profile-last-name">Efternamn</Label>
                  <Input
                    id="profile-last-name"
                    value={form.lastName}
                    onChange={(e) => updateField("lastName", e.target.value)}
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor="profile-email">E-postadress</Label>
                  <Input
                    id="profile-email"
                    type="email"
                    value={form.email}
                    onChange={(e) => updateField("email", e.target.value)}
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor="profile-phone">Telefonnummer</Label>
                  <Input
                    id="profile-phone"
                    value={form.phone}
                    onChange={(e) => updateField("phone", e.target.value)}
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="flex flex-col gap-5 p-6">
              <div>
                <h2 className="text-base font-semibold">Systeminställningar & Språk</h2>
                <p className="text-xs text-muted-foreground">
                  Anpassa hur tidsstämplar visas för ditt konto.
                </p>
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="grid gap-1.5">
                  <Label>Gränssnittsspråk</Label>
                  <Input disabled value="Svenska (SE)" />
                  <p className="text-[11px] text-muted-foreground">Fler språk kommer snart.</p>
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor="profile-timezone">Tidszon</Label>
                  <Select
                    value={form.timezone}
                    onValueChange={(value) => updateField("timezone", value)}
                  >
                    <SelectTrigger id="profile-timezone">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {TIMEZONES.map((tz) => (
                        <SelectItem key={tz} value={tz}>
                          {tz}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="flex flex-col gap-5 p-6">
              <div>
                <h2 className="text-base font-semibold">Säkerhet & Lösenordsbyte</h2>
                <p className="text-xs text-muted-foreground">
                  Det rekommenderas att använda ett starkt lösenord för att skydda ditt
                  operatörskonto.
                </p>
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="profile-current-password">Nuvarande lösenord</Label>
                <Input id="profile-current-password" type="password" />
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="grid gap-1.5">
                  <Label htmlFor="profile-new-password">Nytt lösenord</Label>
                  <Input
                    id="profile-new-password"
                    placeholder="Ange nytt lösenord"
                    type="password"
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor="profile-confirm-password">Bekräfta nytt lösenord</Label>
                  <Input
                    id="profile-confirm-password"
                    placeholder="Bekräfta lösenord"
                    type="password"
                  />
                </div>
              </div>
              <p className="text-[11px] text-muted-foreground">
                Lösenordsbyte stöds inte ännu i denna version.
              </p>
            </CardContent>
          </Card>

          <div>
            <h2 className="mb-2 text-base font-semibold">Utseende</h2>
            <div className="flex gap-2">
              <Button
                variant={theme === "light" ? "default" : "secondary"}
                onClick={() => setTheme("light")}
              >
                Ljust läge
              </Button>
              <Button
                variant={theme === "dark" ? "default" : "secondary"}
                onClick={() => setTheme("dark")}
              >
                Mörkt läge
              </Button>
            </div>
          </div>

          <div className="flex items-center justify-end gap-3">
            {savedNotice ? <Badge variant="outline">Sparat</Badge> : null}
            <Button variant="outline" onClick={cancelChanges}>
              Avbryt
            </Button>
            <Button onClick={saveProfile}>Spara ändringar</Button>
          </div>
        </div>
      </div>

      <Dialog open={Boolean(unavailableNotice)} onOpenChange={() => setUnavailableNotice(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Inte tillgängligt ännu</DialogTitle>
            <DialogDescription>{unavailableNotice}</DialogDescription>
          </DialogHeader>
        </DialogContent>
      </Dialog>
    </PageShell>
  );
}
