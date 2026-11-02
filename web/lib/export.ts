import type { ResearchResult } from "./types";

function tableText(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\\/g, "&#92;")
    .replace(/\|/g, "&#124;")
    .replace(/\r?\n/g, " ");
}

function quoteLines(value: string): string {
  return value
    .split(/\r?\n/)
    .map((line) => `> ${line}`)
    .join("\n");
}

export function markdownReport(result: ResearchResult): string {
  const lines = [
    `# ${result.question}`,
    "",
    `Status: ${result.status} | Retrieved: ${result.created_at}`,
    "",
    "Citation quotes establish source provenance; they are not independent fact checks.",
    "",
  ];
  if (result.coverage.length) {
    const subjects = [
      ...new Set(
        result.coverage.flatMap((row) => row.cells.map((cell) => cell.subject)),
      ),
    ];
    lines.push(
      "## Requested coverage",
      "",
      "Source-reported values may use different scopes and are not necessarily comparable. Inspect quotes for units, definitions, and measurement dates. Publication dates describe the source, not the measurement.",
      "",
      `| Dimension | ${subjects.map(tableText).join(" | ")} |`,
      `| --- | ${subjects.map(() => "---").join(" | ")} |`,
    );
    for (const row of result.coverage) {
      const cells = subjects.map((subject) => {
        const cell = row.cells.find((entry) => entry.subject === subject);
        if (!cell || cell.status === "missing") return "Not found";
        return cell.values
          .map((entry) =>
            tableText(
              `${entry.value} [${entry.citation.source_id}] (Published: ${entry.published_at ?? "Date unavailable"})`,
            ),
          )
          .join("; ");
      });
      lines.push(`| ${tableText(row.label)} | ${cells.join(" | ")} |`);
    }
    lines.push("", "### Coverage provenance", "");
    for (const row of result.coverage) {
      for (const cell of row.cells) {
        for (const entry of cell.values) {
          const source = result.sources.find(
            (item) => item.id === entry.citation.source_id,
          );
          lines.push(
            `${row.label} / ${cell.subject}: ${entry.value}`,
            `Published: ${entry.published_at ?? "Date unavailable"}`,
            "",
            quoteLines(entry.citation.quote),
            "",
            source
              ? `[${source.id}: ${source.title}](${source.url})`
              : entry.citation.source_id,
            "",
          );
        }
      }
    }
  }
  for (const section of ["summary", "finding"]) {
    const claims = result.claims.filter((claim) => claim.section === section);
    if (!claims.length) continue;
    lines.push(
      `## ${section === "summary" ? "Executive summary" : "Findings"}`,
      "",
    );
    for (const claim of claims) {
      lines.push(claim.text, "");
      for (const citation of claim.citations) {
        const source = result.sources.find((s) => s.id === citation.source_id);
        lines.push(
          quoteLines(citation.quote),
          "",
          source ? `[${source.title}](${source.url})` : citation.source_id,
          "",
        );
      }
    }
  }
  if (!result.claims.length) {
    lines.push("## Retrieved evidence", "");
    for (const passage of result.passages) {
      const source = result.sources.find((s) => s.id === passage.source_id);
      lines.push(
        quoteLines(passage.quote),
        "",
        source ? `[${source.title}](${source.url})` : passage.source_id,
        "",
      );
    }
  }
  if (result.conflicts.length) {
    lines.push("## Candidate disagreements requiring review", "");
    for (const conflict of result.conflicts)
      lines.push(
        `### ${conflict.title}`,
        "",
        conflict.explanation,
        "",
        ...[conflict.left, conflict.right].flatMap((citation) => {
          const source = result.sources.find(
            (item) => item.id === citation.source_id,
          );
          return [
            quoteLines(citation.quote),
            "",
            source
              ? `[${source.id}: ${source.title}](${source.url})`
              : citation.source_id,
            "",
          ];
        }),
      );
  }
  if (result.gaps.length)
    lines.push(
      "## Limitations",
      "",
      ...result.gaps.map((gap) => `- ${gap}`),
      "",
    );
  lines.push(
    "## Sources",
    "",
    ...result.sources.map(
      (s) =>
        `- [${s.title}](${s.url}) — ${s.source_type.replaceAll("_", " ")}; published ${s.published_at ?? "Date unavailable"}; retrieved ${s.retrieved_at}`,
    ),
  );
  return lines.join("\n");
}
