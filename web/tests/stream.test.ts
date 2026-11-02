import { test } from "node:test";
import assert from "node:assert/strict";
import { readEvents } from "../lib/stream";
import { markdownReport } from "../lib/export";
import { resultSchema } from "../lib/types";

function body(chunks: string[]) {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks)
        controller.enqueue(new TextEncoder().encode(chunk));
      controller.close();
    },
  });
}

test("reads events split across network chunks", async () => {
  const events = [];
  for await (const event of readEvents(
    body([
      '{"type":"lo',
      'g","stage":"search","message":"Searching","level":"info","elapsed":0}\n',
      '{"type":"error","stage":"error","message":"No sources","level":"error","elapsed":1}',
    ]),
  ))
    events.push(event);
  assert.deepEqual(
    events.map((e) => e.type),
    ["log", "error"],
  );
});

test("rejects malformed events rather than rendering unvalidated data", async () => {
  await assert.rejects(async () => {
    for await (const event of readEvents(
      body(['{"type":"result","result":{"claims":"invented"}}\n']),
    ))
      void event;
  });
});

test("does not silently accept a truncated stream", async () => {
  await assert.rejects(async () => {
    for await (const event of readEvents(
      body(['{"type":"log","stage":"search","message":"Working"}\n']),
    ))
      void event;
  }, /ended/);
});

test("releases the reader lock even when stream cancellation fails", async () => {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(
        new TextEncoder().encode(
          '{"type":"error","stage":"error","message":"Stopped"}\n',
        ),
      );
    },
    cancel() {
      throw new Error("Cancellation failed");
    },
  });
  const iterator = readEvents(stream);
  await iterator.next();
  await assert.rejects(iterator.return(undefined), /Cancellation failed/);
  assert.equal(stream.locked, false);
});

test("Markdown export preserves quote provenance and candidate conflict labels", () => {
  const result = resultSchema.parse({
    id: "run",
    question: "Research question",
    status: "complete",
    queries: [],
    sources: [
      {
        id: "s1",
        title: "Primary source",
        url: "https://example.org/article",
        text: "An exact source quote",
        retrieved_at: "2026-10-31",
      },
    ],
    passages: [],
    claims: [
      {
        text: "A sourced claim",
        section: "summary",
        citations: [{ source_id: "s1", quote: "An exact source quote" }],
      },
    ],
    conflicts: [],
    gaps: [],
    telemetry: {},
    created_at: "2026-10-31",
  });
  const markdown = markdownReport(result);
  assert.ok(markdown.includes("https://example.org/article"));
  assert.ok(markdown.includes("An exact source quote"));
  assert.ok(markdown.includes("A sourced claim"));
});

test("export attributes each conflict passage beside its original source", () => {
  const result = resultSchema.parse({
    id: "conflict-run",
    question: "Compare source counts",
    status: "complete",
    queries: [],
    sources: [
      {
        id: "s1",
        title: "First publisher",
        url: "https://first.example/article",
        text: "The first source reports 193 countries.",
        retrieved_at: "2026-10-31",
      },
      {
        id: "s2",
        title: "Second publisher",
        url: "https://second.example/article",
        text: "The second source reports 195 countries.",
        retrieved_at: "2026-10-31",
      },
    ],
    passages: [],
    claims: [],
    conflicts: [
      {
        title: "Different recognition criteria",
        explanation: "Counts include different state categories.",
        kind: "scope",
        left: {
          source_id: "s1",
          quote: "The first source reports 193 countries.",
        },
        right: {
          source_id: "s2",
          quote: "The second source reports 195 countries.",
        },
      },
    ],
    gaps: [],
    telemetry: {},
    created_at: "2026-10-31",
  });
  const conflictSection = markdownReport(result)
    .split("## Candidate disagreements requiring review")[1]
    .split("## Sources")[0];
  assert.ok(
    conflictSection.includes(
      "[s1: First publisher](https://first.example/article)",
    ),
  );
  assert.ok(
    conflictSection.includes(
      "[s2: Second publisher](https://second.example/article)",
    ),
  );
});
