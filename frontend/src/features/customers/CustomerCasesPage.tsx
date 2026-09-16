import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import { PageShell } from "@/components/patterns/PageShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { apiGet, type CaseListItem } from "@/shared/api/client";

/**
 * Every case linked to one sender/customer, keyed by their email rather
 * than a CRM contacts.id - unlike CustomersPage (which only lists real CRM
 * contacts), this works for anyone who has ever emailed in, CRM record or
 * not. Farah (farah@qinora.org) never got a CRM contact created (Miles
 * Match found no match), so she never appeared as a selectable "customer"
 * anywhere in the app even though her cases existed - reproduced live
 * 2026-09-16.
 */
export function CustomerCasesPage() {
  const { email = "" } = useParams<{ email: string }>();
  const decodedEmail = decodeURIComponent(email);
  const navigate = useNavigate();

  const query = useQuery({
    queryKey: ["cases"],
    queryFn: () => apiGet<CaseListItem[]>("/cases"),
  });

  const cases = (query.data ?? []).filter(
    (item) => item.customer.trim().toLowerCase() === decodedEmail.trim().toLowerCase(),
  );

  return (
    <PageShell subtitle={decodedEmail} title="Kundprofil">
      <Card>
        <CardContent className="flex flex-col gap-4 p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold">Alla ärenden ({cases.length})</h2>
          </div>
          {query.isLoading ? (
            <div className="grid gap-2">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : cases.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Inga ärenden hittades för {decodedEmail}.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-border/60 text-left text-[11px] uppercase text-muted-foreground">
                    <th className="pb-2 font-semibold">Ärende-ID</th>
                    <th className="pb-2 font-semibold">Rutt</th>
                    <th className="pb-2 font-semibold">Kategori</th>
                    <th className="pb-2 font-semibold">Status</th>
                    <th className="pb-2 font-semibold" />
                  </tr>
                </thead>
                <tbody>
                  {cases.map((item) => (
                    <tr className="border-b border-border/30" key={item.id}>
                      <td className="py-3 font-mono font-semibold">{item.public_id}</td>
                      <td className="py-3">{item.lane}</td>
                      <td className="py-3 text-muted-foreground">{item.category}</td>
                      <td className="py-3 text-muted-foreground">{item.status}</td>
                      <td className="py-3 text-right">
                        <Button
                          onClick={() => navigate(`/cases/${item.id}`)}
                          size="sm"
                          variant="outline"
                        >
                          Öppna
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </PageShell>
  );
}
