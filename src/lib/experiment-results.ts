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
  { key: "valid", label: "Valid", direction: "higher", ranked: true },
  { key: "noCollisions", label: "No collisions", direction: "higher", ranked: true },
  { key: "noFloaters", label: "No floaters", direction: "higher", ranked: true },
  { key: "components", label: "Components", direction: "lower", ranked: true },
  { key: "vqa", label: "VQA", direction: "higher", ranked: true },
  { key: "perceptionEncoder", label: "Perception Encoder", direction: "higher", ranked: true },
  { key: "siglip2", label: "SigLIP 2", direction: "higher", ranked: true },
  { key: "parts", label: "Parts", direction: null, ranked: false },
  { key: "uniqueParts", label: "Unique parts", direction: null, ranked: false },
  { key: "checks", label: "Checks", direction: "lower", ranked: true },
  { key: "time", label: "Time", direction: "lower", ranked: false },
  { key: "cost", label: "Cost", direction: "lower", ranked: false },
] as const satisfies {
  key: string;
  label: string;
  direction: MetricDirection | null;
  ranked: boolean;
}[];

export type MetricKey = (typeof metricColumns)[number]["key"];

export interface ResultMetric {
  value: string;
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
      parts: { value: "144.8" },
      uniqueParts: { value: "7.1" },
      checks: { value: "—" },
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
      parts: { value: "31.8" },
      uniqueParts: { value: "11.5" },
      checks: { value: "—" },
      time: { value: "5s" },
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
      parts: { value: "12.8" },
      uniqueParts: { value: "5.3" },
      checks: { value: "—" },
      time: { value: "168s" },
      cost: { value: "$0.04" },
    },
  },
  {
    agent: "haiku",
    method: "BrickWright w/o assembly API",
    metrics: {
      valid: { value: "0.822", emphasis: "underline" },
      noCollisions: { value: "0.889", emphasis: "underline" },
      noFloaters: { value: "0.828", emphasis: "underline" },
      components: { value: "2.07", emphasis: "underline" },
      vqa: { value: "0.5744" },
      perceptionEncoder: { value: "0.2940" },
      siglip2: { value: "0.7009" },
      parts: { value: "16.6" },
      uniqueParts: { value: "4.8" },
      checks: { value: "9.29", emphasis: "underline" },
      time: { value: "279s" },
      cost: { value: "$0.13" },
    },
  },
  {
    agent: "haiku",
    method: "BrickWright w/o validator",
    metrics: {
      valid: { value: "0.586" },
      noCollisions: { value: "0.744" },
      noFloaters: { value: "0.775" },
      components: { value: "2.99" },
      vqa: { value: "0.6390", emphasis: "underline" },
      perceptionEncoder: { value: "0.3012", emphasis: "underline" },
      siglip2: { value: "0.7481", emphasis: "underline" },
      parts: { value: "18.3" },
      uniqueParts: { value: "7.4" },
      checks: { value: "—" },
      time: { value: "119s" },
      cost: { value: "$0.03" },
    },
  },
  {
    agent: "haiku",
    method: "BrickWright",
    metrics: {
      valid: { value: "1.000", emphasis: "bold" },
      noCollisions: { value: "1.000", emphasis: "bold" },
      noFloaters: { value: "1.000", emphasis: "bold" },
      components: { value: "1.00", emphasis: "bold" },
      vqa: { value: "0.6523", emphasis: "bold" },
      perceptionEncoder: { value: "0.3056", emphasis: "bold" },
      siglip2: { value: "0.7660", emphasis: "bold" },
      parts: { value: "21.5" },
      uniqueParts: { value: "7.6" },
      checks: { value: "2.89", emphasis: "bold" },
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
      parts: { value: "21.1" },
      uniqueParts: { value: "6.1" },
      checks: { value: "—" },
      time: { value: "150s" },
      cost: { value: "$0.02" },
    },
  },
  {
    agent: "luna",
    method: "BrickWright w/o assembly API",
    metrics: {
      valid: { value: "0.996", emphasis: "underline" },
      noCollisions: { value: "1.000", emphasis: "bold" },
      noFloaters: { value: "0.996", emphasis: "underline" },
      components: { value: "1.04", emphasis: "underline" },
      vqa: { value: "0.3342" },
      perceptionEncoder: { value: "0.2586" },
      siglip2: { value: "0.4972" },
      parts: { value: "7.2" },
      uniqueParts: { value: "2.0" },
      checks: { value: "15.25", emphasis: "underline" },
      time: { value: "405s" },
      cost: { value: "$0.06" },
    },
  },
  {
    agent: "luna",
    method: "BrickWright w/o validator",
    metrics: {
      valid: { value: "0.529" },
      noCollisions: { value: "0.561", emphasis: "underline" },
      noFloaters: { value: "0.840" },
      components: { value: "2.03" },
      vqa: { value: "0.6975", emphasis: "bold" },
      perceptionEncoder: { value: "0.3111", emphasis: "bold" },
      siglip2: { value: "0.7920", emphasis: "bold" },
      parts: { value: "28.5" },
      uniqueParts: { value: "8.5" },
      checks: { value: "—" },
      time: { value: "510s" },
      cost: { value: "$0.03" },
    },
  },
  {
    agent: "luna",
    method: "BrickWright",
    metrics: {
      valid: { value: "1.000", emphasis: "bold" },
      noCollisions: { value: "1.000", emphasis: "bold" },
      noFloaters: { value: "1.000", emphasis: "bold" },
      components: { value: "1.00", emphasis: "bold" },
      vqa: { value: "0.6945", emphasis: "underline" },
      perceptionEncoder: { value: "0.3105", emphasis: "underline" },
      siglip2: { value: "0.7766", emphasis: "underline" },
      parts: { value: "27.4" },
      uniqueParts: { value: "7.8" },
      checks: { value: "4.62", emphasis: "bold" },
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
      perceptionEncoder: { value: "0.3241", emphasis: "underline" },
      siglip2: { value: "0.8700", emphasis: "bold" },
      parts: { value: "75.9" },
      uniqueParts: { value: "15.8" },
      checks: { value: "—" },
      time: { value: "346s" },
      cost: { value: "$0.29" },
    },
  },
  {
    agent: "sol",
    method: "BrickWright w/o assembly API",
    metrics: {
      valid: { value: "1.000", emphasis: "bold" },
      noCollisions: { value: "1.000", emphasis: "bold" },
      noFloaters: { value: "1.000", emphasis: "bold" },
      components: { value: "1.01", emphasis: "underline" },
      vqa: { value: "0.7623", emphasis: "bold" },
      perceptionEncoder: { value: "0.3228" },
      siglip2: { value: "0.8573" },
      parts: { value: "70.1" },
      uniqueParts: { value: "13.9" },
      checks: { value: "10.02", emphasis: "underline" },
      time: { value: "459s" },
      cost: { value: "$0.40" },
    },
  },
  {
    agent: "sol",
    method: "BrickWright w/o validator",
    metrics: {
      valid: { value: "0.779", emphasis: "underline" },
      noCollisions: { value: "0.787", emphasis: "underline" },
      noFloaters: { value: "0.990", emphasis: "underline" },
      components: { value: "1.03" },
      vqa: { value: "0.7611", emphasis: "underline" },
      perceptionEncoder: { value: "0.3240" },
      siglip2: { value: "0.8664" },
      parts: { value: "86.0" },
      uniqueParts: { value: "19.6" },
      checks: { value: "—" },
      time: { value: "328s" },
      cost: { value: "$0.20" },
    },
  },
  {
    agent: "sol",
    method: "BrickWright",
    metrics: {
      valid: { value: "1.000", emphasis: "bold" },
      noCollisions: { value: "1.000", emphasis: "bold" },
      noFloaters: { value: "1.000", emphasis: "bold" },
      components: { value: "1.00", emphasis: "bold" },
      vqa: { value: "0.7610" },
      perceptionEncoder: { value: "0.3243", emphasis: "bold" },
      siglip2: { value: "0.8669", emphasis: "underline" },
      parts: { value: "75.8" },
      uniqueParts: { value: "16.6" },
      checks: { value: "2.48", emphasis: "bold" },
      time: { value: "251s" },
      cost: { value: "$0.19" },
    },
  },
  {
    agent: "astra",
    method: "Codex",
    metrics: {
      valid: { value: "0.693", emphasis: "underline" },
      noCollisions: { value: "0.709", emphasis: "underline" },
      noFloaters: { value: "0.822" },
      components: { value: "1.87" },
      vqa: { value: "0.7609" },
      perceptionEncoder: { value: "0.3237" },
      siglip2: { value: "0.8691" },
      parts: { value: "75.5" },
      uniqueParts: { value: "15.3" },
      checks: { value: "—" },
      time: { value: "244s" },
      cost: { value: "$1.21" },
    },
  },
  {
    agent: "astra",
    method: "Articraft",
    metrics: {
      valid: { value: "0.684" },
      noCollisions: { value: "0.693" },
      noFloaters: { value: "0.844", emphasis: "underline" },
      components: { value: "1.77", emphasis: "underline" },
      vqa: { value: "0.7690", emphasis: "underline" },
      perceptionEncoder: { value: "0.3249", emphasis: "bold" },
      siglip2: { value: "0.8785", emphasis: "bold" },
      parts: { value: "63.2" },
      uniqueParts: { value: "16.0" },
      checks: { value: "—" },
      time: { value: "426s" },
      cost: { value: "$3.00" },
    },
  },
  {
    agent: "astra",
    method: "BrickWright",
    metrics: {
      valid: { value: "1.000", emphasis: "bold" },
      noCollisions: { value: "1.000", emphasis: "bold" },
      noFloaters: { value: "1.000", emphasis: "bold" },
      components: { value: "1.00", emphasis: "bold" },
      vqa: { value: "0.7695", emphasis: "bold" },
      perceptionEncoder: { value: "0.3243", emphasis: "underline" },
      siglip2: { value: "0.8698", emphasis: "underline" },
      parts: { value: "89.3" },
      uniqueParts: { value: "18.9" },
      checks: { value: "2.40", emphasis: "bold" },
      time: { value: "267s" },
      cost: { value: "$1.28" },
    },
  },
];

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
