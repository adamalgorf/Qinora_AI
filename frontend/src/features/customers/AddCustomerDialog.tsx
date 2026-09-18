import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
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
import { Textarea } from "@/components/ui/textarea";
import {
  apiPost,
  type ApiProblem,
  type ContactCreatePayload,
  type ContactListItem,
} from "@/shared/api/client";

const EMPTY_CUSTOMER = {
  displayName: "",
  email: "",
  domain: "",
  markupPercent: "",
  incoterms: "",
  paymentTerms: "",
  segment: "",
  customerSince: "",
  slaHours: "",
  accountOwner: "",
  healthStatus: "good" as ContactListItem["health_status"],
  annualVolume: "",
  customsContactName: "",
  customsContactEmail: "",
  contractNote: "",
};

type CustomerForm = typeof EMPTY_CUSTOMER;

export function AddCustomerDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (contact: ContactListItem) => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<CustomerForm>(EMPTY_CUSTOMER);

  const createMutation = useMutation<ContactListItem, ApiProblem, ContactCreatePayload>({
    mutationFn: (payload) => apiPost<ContactListItem, ContactCreatePayload>("/contacts", payload),
    onSuccess: async (contact) => {
      await queryClient.invalidateQueries({ queryKey: ["contacts"] });
      onCreated(contact);
      close();
    },
  });

  function close() {
    setForm(EMPTY_CUSTOMER);
    createMutation.reset();
    onOpenChange(false);
  }

  function field<K extends keyof CustomerForm>(key: K) {
    return {
      value: form[key],
      onChange: (event: { target: { value: string } }) =>
        setForm((current) => ({ ...current, [key]: event.target.value })),
    };
  }

  function submit() {
    createMutation.mutate({
      display_name: form.displayName.trim(),
      email: optionalText(form.email),
      domain: optionalText(form.domain),
      default_markup_percent: optionalNumber(form.markupPercent),
      default_incoterms: optionalText(form.incoterms),
      payment_terms: optionalText(form.paymentTerms),
      segment: optionalText(form.segment),
      customer_since: optionalText(form.customerSince),
      sla_tolerance_hours: optionalNumber(form.slaHours),
      account_owner: optionalText(form.accountOwner),
      health_status: form.healthStatus,
      annual_volume_estimate: optionalNumber(form.annualVolume),
      customs_contact_name: optionalText(form.customsContactName),
      customs_contact_email: optionalText(form.customsContactEmail),
      contract_note: optionalText(form.contractNote),
    });
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? onOpenChange(true) : close())}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Lägg till kund</DialogTitle>
          <DialogDescription>
            E-postadressen och domänen används för att automatiskt koppla inkommande mejl till
            kunden. Domänen fylls i från e-postadressen om du lämnar den tom.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 sm:grid-cols-2">
          <FormField className="sm:col-span-2" id="customer-name" label="Kundnamn *">
            <Input id="customer-name" {...field("displayName")} />
          </FormField>
          <FormField id="customer-email" label="E-postadress">
            <Input id="customer-email" type="email" {...field("email")} />
          </FormField>
          <FormField id="customer-domain" label="Domän">
            <Input id="customer-domain" placeholder="foretag.se" {...field("domain")} />
          </FormField>
          <FormField id="customer-segment" label="Segment">
            <Input id="customer-segment" placeholder="t.ex. Fordon" {...field("segment")} />
          </FormField>
          <FormField id="customer-owner" label="Ansvarig">
            <Input id="customer-owner" {...field("accountOwner")} />
          </FormField>
          <FormField id="customer-markup" label="Påslag (%)">
            <Input id="customer-markup" min={0} placeholder="0" type="number" {...field("markupPercent")} />
          </FormField>
          <FormField id="customer-incoterms" label="Incoterms">
            <Input id="customer-incoterms" placeholder="DAP" {...field("incoterms")} />
          </FormField>
          <FormField id="customer-payment-terms" label="Betalningsvillkor">
            <Input id="customer-payment-terms" placeholder="30 dagar netto" {...field("paymentTerms")} />
          </FormField>
          <FormField id="customer-since" label="Kund sedan">
            <Input id="customer-since" type="date" {...field("customerSince")} />
          </FormField>
          <FormField id="customer-sla" label="SLA-tolerans (h)">
            <Input id="customer-sla" min={0} type="number" {...field("slaHours")} />
          </FormField>
          <FormField id="customer-volume" label="Årlig volym (SEK)">
            <Input id="customer-volume" min={0} type="number" {...field("annualVolume")} />
          </FormField>
          <FormField id="customer-health" label="Hälsa">
            <Select
              value={form.healthStatus}
              onValueChange={(value) =>
                setForm((current) => ({
                  ...current,
                  healthStatus: value as ContactListItem["health_status"],
                }))
              }
            >
              <SelectTrigger id="customer-health">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="good">Bra</SelectItem>
                <SelectItem value="watch">Bevaka</SelectItem>
                <SelectItem value="at_risk">I riskzon</SelectItem>
              </SelectContent>
            </Select>
          </FormField>
          <FormField id="customer-customs-name" label="Tullkontakt">
            <Input id="customer-customs-name" {...field("customsContactName")} />
          </FormField>
          <FormField id="customer-customs-email" label="Tullkontakt e-post">
            <Input id="customer-customs-email" type="email" {...field("customsContactEmail")} />
          </FormField>
          <FormField className="sm:col-span-2" id="customer-contract" label="Avtalsnotering">
            <Textarea id="customer-contract" rows={3} {...field("contractNote")} />
          </FormField>
        </div>

        {createMutation.error ? (
          <p className="text-sm text-destructive">
            {typeof createMutation.error.detail === "string"
              ? createMutation.error.detail
              : "Kunde inte skapa kunden. Kontrollera fälten och försök igen."}
          </p>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={close}>
            Avbryt
          </Button>
          <Button disabled={!form.displayName.trim() || createMutation.isPending} onClick={submit}>
            {createMutation.isPending ? "Skapar…" : "Skapa kund"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function FormField({
  id,
  label,
  className,
  children,
}: {
  id: string;
  label: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={`grid gap-1.5 ${className ?? ""}`}>
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  );
}

function optionalText(value: string): string | undefined {
  return value.trim() || undefined;
}

function optionalNumber(value: string): number | undefined {
  const trimmed = value.trim().replace(",", ".");
  return trimmed ? Number(trimmed) : undefined;
}
