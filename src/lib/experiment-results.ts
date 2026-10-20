export const agents = [
  { value: "haiku", slug: "claude-haiku-5-5", label: "Claude Haiku 5.5", baseline: "Claude Code" },
  { value: "luna", slug: "gpt-6-luna", label: "GPT-6 Luna", baseline: "Codex" },
  { value: "sol", slug: "gpt-6-1-sol", label: "GPT-6.1 Sol", baseline: "Codex" },
  { value: "astra", slug: "gpt-6-astra", label: "GPT-6 Astra", baseline: "Codex" },
] as const;

export type Agent = (typeof agents)[number];
export type AgentId = Agent["value"];

export const prompts = [
  {
    id: "80",
    slug: "atv",
    title: "ATV",
    caption:
      "This is a LEGO build of a blue, grey, and black all-terrain vehicle (ATV) or quad bike, featuring large treaded wheels, a roll cage, and translucent yellow headlights.",
  },
  {
    id: "123",
    slug: "utility-helicopter",
    title: "Copter",
    caption:
      "This is a LEGO build of a blue and white utility helicopter, featuring an open cockpit, black landing skids, and a tail rotor.",
  },
  {
    id: "217",
    slug: "insectoid-creature",
    title: "Bug",
    caption:
      "This is a custom-built LEGO build of a fantastical, insectoid creature, constructed primarily from dark blue and black pieces with vibrant magenta accents for its claws, tail stinger, and decorative elements, showcased from multiple angles to highlight its articulated limbs and unique design.",
  },
  {
    id: "114",
    slug: "sitting-fox",
    title: "Fox",
    caption:
      "This is a stylized, geometric LEGO build of a sitting fox, constructed primarily from orange bricks with white accents on the chest and snout, black pieces for the paws and nose, and small orange slopes for ears.",
  },
  {
    id: "41",
    slug: "ninja",
    title: "Ninja",
    caption:
      "This is a blocky, stylized LEGO minifigure of a ninja or martial artist, constructed primarily from black bricks with white and brown accents for its headband and torso, and posed dynamically as if in mid-action.",
  },
  {
    id: "283",
    slug: "white-flowers",
    title: "Flowers",
    caption:
      "This LEGO build is a modular, multi-angle representation of a cluster of white flowers with green leaves and stems, constructed from various specialized plant-themed pieces.",
  },
  {
    id: "277",
    slug: "backyard-scene",
    title: "Scene",
    caption:
      "This LEGO build depicts a small, fenced-in backyard scene featuring a brown shed with an attached silo, a blue pond, green landscaping, and a colorful, abstract sculpture.",
  },
  {
    id: "7",
    slug: "espresso-machine",
    title: "Coffee Machine",
    caption:
      "This LEGO build is a detailed, dual-grouphead espresso machine with an attached coffee grinder, all mounted on a brown baseplate.",
  },
] as const;

export type ResultPrompt = (typeof prompts)[number];

export type MetricDirection = "higher" | "lower";

export const metricColumns = [
  { key: "valid", label: "Valid", direction: "higher" },
  { key: "noCollisions", label: "No collisions", direction: "higher" },
  { key: "noFloaters", label: "No floaters", direction: "higher" },
  { key: "components", label: "Components", direction: "lower" },
  { key: "vqa", label: "VQA", direction: "higher" },
  { key: "perceptionEncoder", label: "Perception Encoder", direction: "higher" },
  { key: "siglip2", label: "SigLIP 2", direction: "higher" },
  { key: "bricks", label: "Bricks", direction: null },
  { key: "time", label: "Time", direction: "lower" },
  { key: "cost", label: "Cost", direction: "lower" },
] as const satisfies { key: string; label: string; direction: MetricDirection | null }[];

export type MetricKey = (typeof metricColumns)[number]["key"];

export interface ResultMetric {
  value: string;
  change?: string;
  emphasis?: "bold" | "underline";
}

export interface QuantitativeResult {
  agent: AgentId | null;
  method: string;
  metrics: Record<MetricKey, ResultMetric>;
}

// Emphasis is explicit: preserve the published markings instead of recomputing rankings.
export const results: QuantitativeResult[] = [
  {
    agent: null,
    method: "BrickGPT",
    metrics: {
      valid: { value: "0.990" },
      noCollisions: { value: "1.000" },
      noFloaters: { value: "0.990" },
      components: { value: "2.67" },
      vqa: { value: "0.0658" },
      perceptionEncoder: { value: "0.1547" },
      siglip2: { value: "0.0514" },
      bricks: { value: "144.8" },
      time: { value: "247s" },
      cost: { value: "—" },
    },
  },
  {
    agent: null,
    method: "BrickNet",
    metrics: {
      valid: { value: "0.318" },
      noCollisions: { value: "0.320" },
      noFloaters: { value: "0.943" },
      components: { value: "1.03" },
      vqa: { value: "0.6077" },
      perceptionEncoder: { value: "0.2846" },
      siglip2: { value: "0.6407" },
      bricks: { value: "31.8" },
      time: { value: "—" },
      cost: { value: "—" },
    },
  },
  {
    agent: "haiku",
    method: "Claude Code",
    metrics: {
      valid: { value: "0.328" },
      noCollisions: { value: "0.428" },
      noFloaters: { value: "0.387" },
      components: { value: "3.59" },
      vqa: { value: "0.6032" },
      perceptionEncoder: { value: "0.2963" },
      siglip2: { value: "0.7286" },
      bricks: { value: "12.8" },
      time: { value: "168s" },
      cost: { value: "$0.04" },
    },
  },
  {
    agent: "haiku",
    method: "BrickWright",
    metrics: {
      valid: { value: "1.000", change: "+0.672", emphasis: "bold" },
      noCollisions: { value: "1.000", change: "+0.572", emphasis: "bold" },
      noFloaters: { value: "1.000", change: "+0.613", emphasis: "bold" },
      components: { value: "1.00", change: "-2.59", emphasis: "bold" },
      vqa: { value: "0.6523", change: "+0.0491" },
      perceptionEncoder: { value: "0.3056", change: "+0.0093" },
      siglip2: { value: "0.7660", change: "+0.0374" },
      bricks: { value: "21.5" },
      time: { value: "143s" },
      cost: { value: "$0.05" },
    },
  },
  {
    agent: "luna",
    method: "Codex",
    metrics: {
      valid: { value: "0.086" },
      noCollisions: { value: "0.131" },
      noFloaters: { value: "0.135" },
      components: { value: "10.11" },
      vqa: { value: "0.6504" },
      perceptionEncoder: { value: "0.3025" },
      siglip2: { value: "0.7593" },
      bricks: { value: "21.1" },
      time: { value: "150s" },
      cost: { value: "$0.02" },
    },
  },
  {
    agent: "luna",
    method: "BrickWright",
    metrics: {
      valid: { value: "1.000", change: "+0.914", emphasis: "bold" },
      noCollisions: { value: "1.000", change: "+0.869", emphasis: "bold" },
      noFloaters: { value: "1.000", change: "+0.865", emphasis: "bold" },
      components: { value: "1.00", change: "-9.11", emphasis: "bold" },
      vqa: { value: "0.6945", change: "+0.0441" },
      perceptionEncoder: { value: "0.3105", change: "+0.0080" },
      siglip2: { value: "0.7766", change: "+0.0173" },
      bricks: { value: "27.4" },
      time: { value: "415s" },
      cost: { value: "$0.03" },
    },
  },
  {
    agent: "sol",
    method: "Codex",
    metrics: {
      valid: { value: "0.641" },
      noCollisions: { value: "0.654" },
      noFloaters: { value: "0.781" },
      components: { value: "2.00" },
      vqa: { value: "0.7610" },
      perceptionEncoder: { value: "0.3241" },
      siglip2: { value: "0.8700", emphasis: "underline" },
      bricks: { value: "75.9" },
      time: { value: "346s" },
      cost: { value: "$0.29" },
    },
  },
  {
    agent: "sol",
    method: "BrickWright",
    metrics: {
      valid: { value: "1.000", change: "+0.359", emphasis: "bold" },
      noCollisions: { value: "1.000", change: "+0.346", emphasis: "bold" },
      noFloaters: { value: "1.000", change: "+0.219", emphasis: "bold" },
      components: { value: "1.00", change: "-1.00", emphasis: "bold" },
      vqa: { value: "0.7610", change: "+0.0000" },
      perceptionEncoder: { value: "0.3243", change: "+0.0002", emphasis: "underline" },
      siglip2: { value: "0.8669", change: "-0.0031" },
      bricks: { value: "75.8" },
      time: { value: "251s" },
      cost: { value: "$0.19" },
    },
  },
  {
    agent: "astra",
    method: "Codex",
    metrics: {
      valid: { value: "0.693" },
      noCollisions: { value: "0.709" },
      noFloaters: { value: "0.822" },
      components: { value: "1.87" },
      vqa: { value: "0.7609" },
      perceptionEncoder: { value: "0.3237" },
      siglip2: { value: "0.8691" },
      bricks: { value: "75.5" },
      time: { value: "244s" },
      cost: { value: "$1.21" },
    },
  },
  {
    agent: "astra",
    method: "Articraft",
    metrics: {
      valid: { value: "0.684", change: "-0.010" },
      noCollisions: { value: "0.693", change: "-0.016" },
      noFloaters: { value: "0.844", change: "+0.021" },
      components: { value: "1.77", change: "-0.10" },
      vqa: { value: "0.7690", change: "+0.0081", emphasis: "underline" },
      perceptionEncoder: { value: "0.3249", change: "+0.0012", emphasis: "bold" },
      siglip2: { value: "0.8785", change: "+0.0094", emphasis: "bold" },
      bricks: { value: "63.2" },
      time: { value: "426s" },
      cost: { value: "$3.00" },
    },
  },
  {
    agent: "astra",
    method: "BrickWright",
    metrics: {
      valid: { value: "1.000", change: "+0.307", emphasis: "bold" },
      noCollisions: { value: "1.000", change: "+0.291", emphasis: "bold" },
      noFloaters: { value: "1.000", change: "+0.178", emphasis: "bold" },
      components: { value: "1.00", change: "-0.87", emphasis: "bold" },
      vqa: { value: "0.7695", change: "+0.0086", emphasis: "bold" },
      perceptionEncoder: { value: "0.3243", change: "+0.0006", emphasis: "underline" },
      siglip2: { value: "0.8698", change: "+0.0007" },
      bricks: { value: "89.3" },
      time: { value: "267s" },
      cost: { value: "$1.28" },
    },
  },
];

export function changeOutcome(change: string | undefined, direction: MetricDirection | null) {
  const difference = Number(change ?? 0);
  if (difference === 0 || direction === null) return null;
  const improved = direction === "higher" ? difference > 0 : difference < 0;
  return improved ? "improvement" : "regression";
}

export function fullAgentName(agentId: AgentId | null) {
  return agents.find((agent) => agent.value === agentId)?.label ?? "—";
}

export function resultModelName(
  prompt: ResultPrompt,
  agent: Agent,
  method: "baseline" | "brickwright",
) {
  return `${prompt.slug}-${agent.slug}-${method}` as const;
}
