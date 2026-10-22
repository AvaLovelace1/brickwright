import { existsSync, readFileSync } from "node:fs";
import { expect, test } from "vitest";
import provenance from "./assets/models/results/source.json";
import {
  agents,
  prompts,
  results,
  metricColumns,
  fullAgentName,
  resultModelName,
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

        // Provenance may also retain archived comparisons that are no longer displayed.
        const records = provenance.models.filter(
          (model) =>
            model.prompt === prompt.id && model.agent === agent.value && model.method === method,
        );
        expect(records, name).toHaveLength(1);
        expect(records[0].file, name).toBe(`${name}.ldr`);
        const diagnostics = JSON.parse(readFileSync(`${modelPath}.diagnostics.json`, "utf8"));
        // Shared diagnostic tests check the file hash and every rendered placement.
        expect(records[0].modelSha256, name).toBe(diagnostics.modelSha256);
      }
    }
  }
  expect(new Set(filenames).size, "Duplicate download filenames").toBe(filenames.length);
});

test("table rows reference configured agents and provide usable values for every column", () => {
  const agentIds = new Set(agents.map((agent) => agent.value));
  const rowIds = results.map((row) => JSON.stringify([row.agent, row.method]));
  expect(results.length).toBeGreaterThan(0);
  expect(new Set(rowIds).size, "Duplicate agent/method rows").toBe(rowIds.length);

  for (const row of results) {
    if (row.agent !== null)
      expect(agentIds.has(row.agent), `Unknown agent: ${row.agent}`).toBe(true);
    expect(row.method.trim()).not.toBe("");
    for (const column of metricColumns) {
      const context = `${row.agent ?? "standalone"} / ${row.method} / ${column.key}`;
      const cell = row.metrics[column.key];
      expect(cell, context).toBeDefined();
      expect(cell.value.trim(), context).not.toBe("");
    }
  }
});

test("bold and underline mark the best and second-best ranked metrics within each agent", () => {
  const ranked = metricColumns.filter((column) => column.ranked);
  for (const agent of agents) {
    const group = results.filter((row) => row.agent === agent.value);
    for (const column of ranked) {
      const scores = [
        ...new Set(
          group.map((row) => Number(row.metrics[column.key].value)).filter(Number.isFinite),
        ),
      ].sort((a, b) => (column.direction === "higher" ? b - a : a - b));
      for (const row of group) {
        const rank = scores.indexOf(Number(row.metrics[column.key].value));
        const expected = rank === 0 ? "bold" : rank === 1 ? "underline" : undefined;
        expect(
          row.metrics[column.key].emphasis,
          `${agent.value} / ${row.method} / ${column.key}`,
        ).toBe(expected);
      }
    }
  }
  for (const row of results)
    for (const column of metricColumns)
      if (row.agent === null || !column.ranked)
        expect(row.metrics[column.key].emphasis, `${row.method} / ${column.key}`).toBeUndefined();
});
