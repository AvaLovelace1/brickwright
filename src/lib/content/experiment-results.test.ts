import { existsSync, readFileSync } from "node:fs";
import { expect, test } from "vitest";
import provenance from "../assets/models/results/source.json";
import {
  agents,
  prompts,
  results,
  metricColumns,
  fullAgentName,
  metricEmphasis,
  resultModelName,
  type AgentId,
  type MetricKey,
} from "./experiment-results";

const resultDirectory = "src/lib/assets/models/results";

test("catalog identifiers and slugs are non-empty and unique", () => {
  const identifiers = {
    "agent IDs": agents.map((agent) => agent.value),
    "agent slugs": agents.map((agent) => agent.slug),
    "prompt IDs": prompts.map((prompt) => prompt.id),
    "prompt slugs": prompts.map((prompt) => prompt.slug),
    "metric keys": metricColumns.map((column) => column.key),
  };
  for (const [name, values] of Object.entries(identifiers)) {
    expect(values.length, name).toBeGreaterThan(0);
    expect(new Set(values).size, `Duplicate ${name}`).toBe(values.length);
    for (const value of values) expect(value.trim(), name).not.toBe("");
  }
  for (const agent of agents) {
    expect(agent.label.trim()).not.toBe("");
    expect(agent.baseline.trim()).not.toBe("");
    expect(fullAgentName(agent.value)).toBe(agent.label);
  }
  for (const prompt of prompts) {
    expect(prompt.title.trim()).not.toBe("");
    expect(prompt.caption.trim()).not.toBe("");
  }
});

test("displayed comparisons have distinct filenames, all assets, and matching provenance", () => {
  const filenames: string[] = [];
  for (const prompt of prompts) {
    for (const agent of agents) {
      for (const method of ["baseline", "brickwright"] as const) {
        const name = resultModelName(prompt, agent, method);
        filenames.push(name);
        const modelPath = `${resultDirectory}/${name}`;
        for (const extension of ["ldr", "packed.mpd", "diagnostics.json"])
          expect(existsSync(`${modelPath}.${extension}`), `${modelPath}.${extension}`).toBe(true);

        const records = provenance.models.filter(
          (model) =>
            model.prompt === prompt.id && model.agent === agent.value && model.method === method,
        );
        expect(records, name).toHaveLength(1);
        expect(records[0].file, name).toBe(`${name}.ldr`);
        const diagnostics = JSON.parse(readFileSync(`${modelPath}.diagnostics.json`, "utf8"));
        expect(records[0].modelSha256, name).toBe(diagnostics.modelSha256);
      }
    }
  }
  expect(new Set(filenames).size, "Duplicate download filenames").toBe(filenames.length);
});

test("table rows are unique and provide a value for every column", () => {
  const rowIds = results.map((row) => JSON.stringify([row.agent, row.method]));
  expect(results.length).toBeGreaterThan(0);
  expect(new Set(rowIds).size, "Duplicate agent/method rows").toBe(rowIds.length);
  for (const row of results) {
    expect(row.method.trim()).not.toBe("");
    for (const column of metricColumns)
      expect(row.metrics[column.key].trim(), `${row.method} / ${column.key}`).not.toBe("");
  }
});

const emphasis = (agent: AgentId | null, method: string, key: MetricKey) =>
  metricEmphasis(
    results.find((row) => row.agent === agent && row.method === method)!,
    metricColumns.find((column) => column.key === key)!,
  );

test("bold and underline mark the best and second-best ranked scores within each agent", () => {
  expect(emphasis("haiku", "BrickWright", "valid")).toBe("bold");
  expect(emphasis("haiku", "BrickWright w/o assembly API", "valid")).toBe("underline");
  expect(emphasis("haiku", "Claude Code", "valid")).toBeUndefined();
  expect(emphasis("haiku", "BrickWright", "components")).toBe("bold");
  expect(emphasis("haiku", "BrickWright w/o assembly API", "components")).toBe("underline");
  expect(emphasis("haiku", "BrickWright w/o validator", "components")).toBeUndefined();
});

test("tied scores share a mark, and the next distinct score is second best", () => {
  expect(emphasis("luna", "BrickWright", "noCollisions")).toBe("bold");
  expect(emphasis("luna", "BrickWright w/o assembly API", "noCollisions")).toBe("bold");
  expect(emphasis("luna", "BrickWright w/o validator", "noCollisions")).toBe("underline");
});

test("standalone methods, unranked columns, and missing scores are unmarked", () => {
  expect(emphasis(null, "BrickNet", "vqa")).toBeUndefined();
  expect(emphasis("haiku", "BrickWright", "parts")).toBeUndefined();
  expect(emphasis("haiku", "Claude Code", "checks")).toBeUndefined();
});
