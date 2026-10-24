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

export const metricColumns = [
  { key: "valid", label: "Valid", direction: "higher", ranked: true },
  { key: "noCollisions", label: "No collisions", direction: "higher", ranked: true },
  { key: "noFloaters", label: "No floaters", direction: "higher", ranked: true },
  { key: "components", label: "Components", direction: "lower", ranked: true },
  {
    key: "vqa",
    label: "VQA",
    direction: "higher",
    ranked: true,
    href: "https://linzhiqiu.github.io/papers/vqascore/",
  },
  {
    key: "perceptionEncoder",
    label: "Perception Encoder",
    direction: "higher",
    ranked: true,
    href: "https://proceedings.neurips.cc/paper_files/paper/2025/hash/57bc0a850255e2041341bf74c7e2b9fa-Abstract-Conference.html",
  },
  {
    key: "siglip2",
    label: "SigLIP 2",
    direction: "higher",
    ranked: true,
    href: "https://arxiv.org/abs/2502.14786",
  },
  { key: "parts", label: "Parts", direction: null, ranked: false },
  { key: "uniqueParts", label: "Unique parts", direction: null, ranked: false },
  { key: "checks", label: "Checks", direction: "lower", ranked: true },
  { key: "time", label: "Time", direction: "lower", ranked: false },
  { key: "cost", label: "Cost", direction: "lower", ranked: false },
] as const satisfies {
  key: string;
  label: string;
  direction: "higher" | "lower" | null;
  ranked: boolean;
  href?: string;
}[];

export type MetricColumn = (typeof metricColumns)[number];
export type MetricKey = MetricColumn["key"];

export interface QuantitativeResult {
  agent: AgentId | null;
  method: string;
  href?: string;
  metrics: Record<MetricKey, string>;
}

export const results: QuantitativeResult[] = [
  {
    agent: null,
    method: "BrickGPT",
    href: "https://avalovelace1.github.io/BrickGPT/",
    metrics: {
      valid: "0.990",
      noCollisions: "1.000",
      noFloaters: "0.990",
      components: "2.67",
      vqa: "0.0658",
      perceptionEncoder: "0.1547",
      siglip2: "0.0514",
      parts: "144.8",
      uniqueParts: "7.1",
      checks: "—",
      time: "247s",
      cost: "—",
    },
  },
  {
    agent: null,
    method: "BrickNet",
    href: "https://kulits.github.io/BrickNet/",
    metrics: {
      valid: "0.318",
      noCollisions: "0.320",
      noFloaters: "0.943",
      components: "1.03",
      vqa: "0.6077",
      perceptionEncoder: "0.2846",
      siglip2: "0.6407",
      parts: "31.8",
      uniqueParts: "11.5",
      checks: "—",
      time: "5s",
      cost: "—",
    },
  },
  {
    agent: "haiku",
    method: "Claude Code",
    metrics: {
      valid: "0.328",
      noCollisions: "0.428",
      noFloaters: "0.387",
      components: "3.59",
      vqa: "0.6032",
      perceptionEncoder: "0.2963",
      siglip2: "0.7286",
      parts: "12.8",
      uniqueParts: "5.3",
      checks: "—",
      time: "168s",
      cost: "$0.04",
    },
  },
  {
    agent: "haiku",
    method: "BrickWright w/o assembly API",
    metrics: {
      valid: "0.822",
      noCollisions: "0.889",
      noFloaters: "0.828",
      components: "2.07",
      vqa: "0.5744",
      perceptionEncoder: "0.2940",
      siglip2: "0.7009",
      parts: "16.6",
      uniqueParts: "4.8",
      checks: "9.29",
      time: "279s",
      cost: "$0.13",
    },
  },
  {
    agent: "haiku",
    method: "BrickWright w/o validator",
    metrics: {
      valid: "0.586",
      noCollisions: "0.744",
      noFloaters: "0.775",
      components: "2.99",
      vqa: "0.6390",
      perceptionEncoder: "0.3012",
      siglip2: "0.7481",
      parts: "18.3",
      uniqueParts: "7.4",
      checks: "—",
      time: "119s",
      cost: "$0.03",
    },
  },
  {
    agent: "haiku",
    method: "BrickWright",
    metrics: {
      valid: "1.000",
      noCollisions: "1.000",
      noFloaters: "1.000",
      components: "1.00",
      vqa: "0.6523",
      perceptionEncoder: "0.3056",
      siglip2: "0.7660",
      parts: "21.5",
      uniqueParts: "7.6",
      checks: "2.89",
      time: "143s",
      cost: "$0.05",
    },
  },
  {
    agent: "luna",
    method: "Codex",
    metrics: {
      valid: "0.086",
      noCollisions: "0.131",
      noFloaters: "0.135",
      components: "10.11",
      vqa: "0.6504",
      perceptionEncoder: "0.3025",
      siglip2: "0.7593",
      parts: "21.1",
      uniqueParts: "6.1",
      checks: "—",
      time: "150s",
      cost: "$0.02",
    },
  },
  {
    agent: "luna",
    method: "BrickWright w/o assembly API",
    metrics: {
      valid: "0.996",
      noCollisions: "1.000",
      noFloaters: "0.996",
      components: "1.04",
      vqa: "0.3342",
      perceptionEncoder: "0.2586",
      siglip2: "0.4972",
      parts: "7.2",
      uniqueParts: "2.0",
      checks: "15.25",
      time: "405s",
      cost: "$0.06",
    },
  },
  {
    agent: "luna",
    method: "BrickWright w/o validator",
    metrics: {
      valid: "0.529",
      noCollisions: "0.561",
      noFloaters: "0.840",
      components: "2.03",
      vqa: "0.6975",
      perceptionEncoder: "0.3111",
      siglip2: "0.7920",
      parts: "28.5",
      uniqueParts: "8.5",
      checks: "—",
      time: "510s",
      cost: "$0.03",
    },
  },
  {
    agent: "luna",
    method: "BrickWright",
    metrics: {
      valid: "1.000",
      noCollisions: "1.000",
      noFloaters: "1.000",
      components: "1.00",
      vqa: "0.6945",
      perceptionEncoder: "0.3105",
      siglip2: "0.7766",
      parts: "27.4",
      uniqueParts: "7.8",
      checks: "4.62",
      time: "415s",
      cost: "$0.03",
    },
  },
  {
    agent: "sol",
    method: "Codex",
    metrics: {
      valid: "0.641",
      noCollisions: "0.654",
      noFloaters: "0.781",
      components: "2.00",
      vqa: "0.7610",
      perceptionEncoder: "0.3241",
      siglip2: "0.8700",
      parts: "75.9",
      uniqueParts: "15.8",
      checks: "—",
      time: "346s",
      cost: "$0.29",
    },
  },
  {
    agent: "sol",
    method: "BrickWright w/o assembly API",
    metrics: {
      valid: "1.000",
      noCollisions: "1.000",
      noFloaters: "1.000",
      components: "1.01",
      vqa: "0.7623",
      perceptionEncoder: "0.3228",
      siglip2: "0.8573",
      parts: "70.1",
      uniqueParts: "13.9",
      checks: "10.02",
      time: "459s",
      cost: "$0.40",
    },
  },
  {
    agent: "sol",
    method: "BrickWright w/o validator",
    metrics: {
      valid: "0.779",
      noCollisions: "0.787",
      noFloaters: "0.990",
      components: "1.03",
      vqa: "0.7611",
      perceptionEncoder: "0.3240",
      siglip2: "0.8664",
      parts: "86.0",
      uniqueParts: "19.6",
      checks: "—",
      time: "328s",
      cost: "$0.20",
    },
  },
  {
    agent: "sol",
    method: "BrickWright",
    metrics: {
      valid: "1.000",
      noCollisions: "1.000",
      noFloaters: "1.000",
      components: "1.00",
      vqa: "0.7610",
      perceptionEncoder: "0.3243",
      siglip2: "0.8669",
      parts: "75.8",
      uniqueParts: "16.6",
      checks: "2.48",
      time: "251s",
      cost: "$0.19",
    },
  },
  {
    agent: "astra",
    method: "Codex",
    metrics: {
      valid: "0.693",
      noCollisions: "0.709",
      noFloaters: "0.822",
      components: "1.87",
      vqa: "0.7609",
      perceptionEncoder: "0.3237",
      siglip2: "0.8691",
      parts: "75.5",
      uniqueParts: "15.3",
      checks: "—",
      time: "244s",
      cost: "$1.21",
    },
  },
  {
    agent: "astra",
    method: "Articraft",
    href: "https://articraft3d.github.io/",
    metrics: {
      valid: "0.684",
      noCollisions: "0.693",
      noFloaters: "0.844",
      components: "1.77",
      vqa: "0.7690",
      perceptionEncoder: "0.3249",
      siglip2: "0.8785",
      parts: "63.2",
      uniqueParts: "16.0",
      checks: "—",
      time: "426s",
      cost: "$3.00",
    },
  },
  {
    agent: "astra",
    method: "BrickWright",
    metrics: {
      valid: "1.000",
      noCollisions: "1.000",
      noFloaters: "1.000",
      components: "1.00",
      vqa: "0.7695",
      perceptionEncoder: "0.3243",
      siglip2: "0.8698",
      parts: "89.3",
      uniqueParts: "18.9",
      checks: "2.40",
      time: "267s",
      cost: "$1.28",
    },
  },
];

/** Bold marks an agent's best score in a ranked column, and underline its second best; ties share a mark. */
export function metricEmphasis(row: QuantitativeResult, column: MetricColumn) {
  if (row.agent === null || !column.ranked) return undefined;
  const score = (result: QuantitativeResult) => Number(result.metrics[column.key]);
  const scores = [...new Set(results.filter((result) => result.agent === row.agent).map(score))]
    .filter(Number.isFinite)
    .sort((a, b) => (column.direction === "higher" ? b - a : a - b));
  const rank = scores.indexOf(score(row));
  return rank === 0 ? "bold" : rank === 1 ? "underline" : undefined;
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
