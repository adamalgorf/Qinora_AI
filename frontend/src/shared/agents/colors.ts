export type AgentColor = {
  dot: string;
  bg: string;
  text: string;
};

/**
 * Each agent keeps one fixed hue everywhere it appears (admin config, audit
 * trail, workflow activity) - matches the design system's "agents are
 * colleagues with a colour" rule. Reuses --primary/--accent where the
 * agent's role already lines up with that token's semantic meaning; Rex
 * Response gets a dedicated hue since it's a distinct third role.
 */
const AGENT_COLORS: Record<string, AgentColor> = {
  request_parsing_agent: { dot: "bg-accent", bg: "bg-accent/10", text: "text-accent" },
  carrier_offer_agent: { dot: "bg-primary", bg: "bg-primary/10", text: "text-primary" },
  quote_response_agent: {
    dot: "bg-[#853BCE]",
    bg: "bg-[#853BCE]/10",
    text: "text-[#853BCE]",
  },
};

// Historical/demo agent names that predate the current 3-agent lineup, kept
// so seeded demo data still resolves to a sensible colour by role.
const NAME_ALIASES: Record<string, string> = {
  parsek: "request_parsing_agent",
  "remy rates": "carrier_offer_agent",
  "rex response": "quote_response_agent",
  "nora intake": "request_parsing_agent",
  "quinn quote": "carrier_offer_agent",
  "carrier intelligence": "quote_response_agent",
};

const DEFAULT_COLOR: AgentColor = {
  dot: "bg-muted-foreground",
  bg: "bg-muted",
  text: "text-muted-foreground",
};

export function getAgentColor(agentKeyOrName: string): AgentColor {
  const normalized = agentKeyOrName.trim().toLowerCase();
  const key = normalized in AGENT_COLORS ? normalized : (NAME_ALIASES[normalized] ?? "");
  return AGENT_COLORS[key] ?? DEFAULT_COLOR;
}
