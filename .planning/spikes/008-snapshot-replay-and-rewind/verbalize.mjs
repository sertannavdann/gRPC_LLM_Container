// Shared c_state verbalizer for spikes 005a/005b — MUST stay byte-identical in both packages.
//
// Library-agnostic by design: takes canonical "view" records (plain objects) produced by
// each library's adapter and renders them as LLM-legible structured text. The survey's
// finding (structured/programming-language representations beat prose) is tested by
// comparing formats, not libraries — the library question is what it costs to PRODUCE
// canonical views, which is measured in each package's world.mjs.
//
// Canonical ordering rule: sort by logical string id. Entity insertion order and numeric
// eids are NOT stable across churn in either library, so ordering is the verbalizer's job.

export function canonicalize(views) {
  return [...views].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
}

// Format 1: naive pretty JSON dump — what a lazy integration would do.
export function toJsonPretty(views) {
  return JSON.stringify(canonicalize(views), null, 2);
}

// Format 2: compact JSON.
export function toJsonCompact(views) {
  return JSON.stringify(canonicalize(views));
}

// Format 3: schema-headed table (pipe-delimited), one row per entity.
export function toTable(views) {
  const rows = canonicalize(views);
  const header =
    "# pipeline_state schema: id | label | kind | status | lifecycle | cpu_pct | mem_mb | x | y | credentials\n";
  const body = rows
    .map((v) =>
      [
        v.id, v.label, v.kind, v.status, v.lifecycle ?? "-",
        v.cpu, v.mem, v.x, v.y,
        v.credentials.length ? v.credentials.join(",") : "-",
      ].join(" | ")
    )
    .join("\n");
  return header + body;
}

// Format 4: compact DSL grouped by kind — dense, schema-in-prose-header.
export function toCompactDsl(views) {
  const rows = canonicalize(views);
  const groups = new Map();
  for (const v of rows) {
    if (!groups.has(v.kind)) groups.set(v.kind, []);
    groups.get(v.kind).push(v);
  }
  const lines = [
    "# pipeline_state — line format: <id> \"<label>\" <status>[/<lifecycle>] cpu=<pct> mem=<MB> @(<x>,<y>)[ creds:<list>]",
  ];
  for (const kind of [...groups.keys()].sort()) {
    lines.push(`[${kind}]`);
    for (const v of groups.get(kind)) {
      let line = `${v.id} "${v.label}" ${v.status}`;
      if (v.lifecycle) line += `/${v.lifecycle}`;
      line += ` cpu=${v.cpu} mem=${v.mem} @(${v.x},${v.y})`;
      if (v.credentials.length) line += ` creds:${v.credentials.join(",")}`;
      lines.push(line);
    }
  }
  return lines.join("\n");
}

export const FORMATS = {
  "json-pretty": toJsonPretty,
  "json-compact": toJsonCompact,
  "table": toTable,
  "compact-dsl": toCompactDsl,
};
