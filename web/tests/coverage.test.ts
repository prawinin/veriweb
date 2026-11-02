import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Report, Inspector, Sources } from "../app/components";
import { markdownReport } from "../lib/export";
import { resultSchema } from "../lib/types";

const legacy = {
  id: "run",
  question: "Compare A and B costs",
  status: "complete",
  queries: [],
  passages: [],
  claims: [],
  conflicts: [],
  gaps: [],
  telemetry: {},
  created_at: "2026-01-01T00:00:00Z",
  sources: [
    {
      id: "s1",
      title: "Cost report",
      url: "https://example.org/report",
      text: "A costs $12 per month | billed monthly.",
      retrieved_at: "2026-01-01",
    },
  ],
};
const coverage = [
  {
    dimension: "cost",
    label: "Cost | per month",
    kind: "quantitative",
    cells: [
      {
        subject: "A",
        status: "supported",
        values: [
          {
            value: "$12 per month",
            citation: {
              source_id: "s1",
              quote:
                "A costs $12 per month | billed monthly.\nQuoted continuation.",
            },
            published_at: "2025-12-01",
          },
        ],
      },
      { subject: "B", status: "missing", values: [] },
    ],
  },
];

test("legacy history receives empty coverage and descriptive source defaults", () => {
  const result = resultSchema.parse(legacy);
  assert.deepEqual(result.coverage, []);
  assert.equal(result.sources[0].source_type, "other");
  assert.deepEqual(result.sources[0].links, []);
});

test("coverage rejects unsupported cells containing values and supported cells without evidence", () => {
  for (const cell of [
    { ...coverage[0].cells[0], status: "missing" },
    { subject: "A", status: "supported", values: [] },
  ]) {
    assert.equal(
      resultSchema.safeParse({
        ...legacy,
        coverage: [{ ...coverage[0], cells: [cell] }],
      }).success,
      false,
    );
  }
});

test("Markdown preserves requested comparison, missing cells, source URL, full quote and publication date", () => {
  const result = resultSchema.parse({ ...legacy, coverage });
  const markdown = markdownReport(result);
  assert.match(markdown, /\| Dimension \| A \| B \|/);
  assert.match(markdown, /Cost &#124; per month/);
  assert.match(markdown, /Not found/);
  assert.match(markdown, /\$12 per month/);
  assert.match(markdown, /Published: 2025-12-01/);
  assert.match(markdown, /https:\/\/example.org\/report/);
  assert.match(
    markdown,
    /> A costs \$12 per month \| billed monthly\.\n> Quoted continuation\./,
  );
});

test("report renders requested subjects, missing coverage, and inspectable publication provenance before prose", () => {
  const result = resultSchema.parse({
    ...legacy,
    coverage,
    claims: [
      {
        text: "Costs differ.",
        section: "summary",
        citations: [coverage[0].cells[0].values[0].citation],
      },
    ],
  });
  const html = renderToStaticMarkup(
    createElement(Report, { result, onSelect: () => undefined }),
  );
  assert.match(html, /scope="col">A<\/th>/);
  assert.match(html, /scope="col">B<\/th>/);
  assert.match(html, /Not found/);
  assert.match(html, /Published 2025-12-01/);
  assert.match(html, /Inspect source 01 quote/);
  assert.ok(
    html.indexOf("Requested coverage") < html.indexOf("Executive summary"),
  );
  const undated = resultSchema.parse({
    ...legacy,
    coverage: [
      {
        ...coverage[0],
        cells: [
          {
            ...coverage[0].cells[0],
            values: [{ ...coverage[0].cells[0].values[0], published_at: null }],
          },
        ],
      },
    ],
  });
  assert.match(
    renderToStaticMarkup(
      createElement(Report, { result: undated, onSelect: () => undefined }),
    ),
    /Date unavailable/,
  );
});

test("source catalog and inspector describe source kind without a trust rating", () => {
  const result = resultSchema.parse({
    ...legacy,
    sources: [{ ...legacy.sources[0], source_type: "public_institution" }],
  });
  assert.match(
    renderToStaticMarkup(
      createElement(Sources, {
        sources: result.sources,
        onSelect: () => undefined,
      }),
    ),
    /Public institution/,
  );
  assert.match(
    renderToStaticMarkup(
      createElement(Inspector, {
        sources: result.sources,
        result,
        selected: { source_id: "s1", quote: "" },
        onSelect: () => undefined,
      }),
    ),
    /Public institution/,
  );
});
