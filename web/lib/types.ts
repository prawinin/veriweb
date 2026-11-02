import { z } from "zod";

export const sourceSchema = z.object({
  id: z.string().regex(/^s[1-8]$/),
  title: z.string().max(500),
  url: z.url().refine((value) => /^https?:\/\//.test(value)),
  text: z.string().max(100000),
  retrieved_at: z.string(),
  published_at: z.string().nullable().optional(),
  source_type: z
    .enum(["public_institution", "research", "technical", "other"])
    .default("other"),
  links: z
    .array(
      z.object({
        url: z.url().refine((value) => /^https?:\/\//.test(value)),
        title: z.string().min(1).max(200),
      }),
    )
    .max(16)
    .default([]),
});
export const citationSchema = z.object({
  source_id: z.string(),
  quote: z.string().min(15).max(1400),
});
export const coverageValueSchema = z.object({
  value: z.string().min(1).max(200),
  citation: citationSchema,
  published_at: z.string().nullable().default(null),
});
export const coverageCellSchema = z
  .object({
    subject: z.string().min(1).max(200),
    status: z.enum(["supported", "missing"]),
    values: z.array(coverageValueSchema).max(3),
  })
  .refine(
    (cell) =>
      cell.status === "supported"
        ? cell.values.length > 0
        : cell.values.length === 0,
    {
      message:
        "Supported cells require evidence; missing cells cannot contain values",
      path: ["values"],
    },
  );
export const coverageRowSchema = z.object({
  dimension: z.string().min(1).max(200),
  label: z.string().min(1).max(200),
  kind: z.enum(["quantitative", "availability", "date", "qualitative"]),
  cells: z.array(coverageCellSchema).min(1).max(4),
});
export const claimSchema = z.object({
  text: z.string().max(1600),
  section: z.enum(["summary", "finding"]).default("finding"),
  citations: z.array(citationSchema).min(1).max(4),
});
export const conflictSchema = z.object({
  title: z.string(),
  explanation: z.string(),
  kind: z.enum(["numeric", "date", "claim", "scope", "unresolved"]),
  left: citationSchema,
  right: citationSchema,
  left_quantity: z.string().max(80).nullable().optional(),
  right_quantity: z.string().max(80).nullable().optional(),
});
export const passageSchema = z.object({
  id: z.string(),
  source_id: z.string(),
  quote: z.string(),
  start: z.number(),
  end: z.number(),
  score: z.number(),
});
export const telemetrySchema = z.object({
  model: z.string().nullable().optional(),
  backend: z.string().default("unverified"),
  retrieval_seconds: z.number().nullable().optional(),
  generation_seconds: z.number().nullable().optional(),
  tokens_per_second: z.number().nullable().optional(),
  ranking: z.string().default("BM25"),
  paragraphs: z.number().default(0),
});
export const resultSchema = z.object({
  id: z.string(),
  question: z.string(),
  status: z.enum(["complete", "incomplete", "excerpts"]),
  queries: z.array(z.string()),
  sources: z.array(sourceSchema).max(8),
  passages: z.array(passageSchema),
  claims: z.array(claimSchema),
  conflicts: z.array(conflictSchema),
  coverage: z.array(coverageRowSchema).max(6).default([]),
  gaps: z.array(z.string()),
  telemetry: telemetrySchema,
  created_at: z.string(),
});
export const eventSchema = z
  .object({
    type: z.enum(["log", "queries", "source", "result", "error", "heartbeat"]),
    stage: z.string(),
    message: z.string(),
    level: z.enum(["info", "success", "warning", "error"]).default("info"),
    elapsed: z.number().default(0),
    queries: z.array(z.string()).nullable().optional(),
    source: sourceSchema.nullable().optional(),
    result: resultSchema.nullable().optional(),
  })
  .superRefine((event, context) => {
    if (event.type === "result" && !event.result)
      context.addIssue({ code: "custom", message: "Missing research result" });
    if (event.type === "source" && !event.source)
      context.addIssue({ code: "custom", message: "Missing source" });
  });
export const statusSchema = z.object({
  available: z.boolean(),
  model: z.string().nullable(),
  backend: z.string(),
  backend_verified: z.boolean(),
  embeddings: z.boolean(),
  busy: z.boolean(),
  message: z.string(),
});
export type CoverageRow = z.infer<typeof coverageRowSchema>;
export type Source = z.infer<typeof sourceSchema>;
export type Citation = z.infer<typeof citationSchema>;
export type Claim = z.infer<typeof claimSchema>;
export type ResearchResult = z.infer<typeof resultSchema>;
export type RunEvent = z.infer<typeof eventSchema>;
export type ServiceStatus = z.infer<typeof statusSchema>;
