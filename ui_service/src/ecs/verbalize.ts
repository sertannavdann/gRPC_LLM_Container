'use client';

import type { CanvasView } from './types';

/**
 * Canonical c_state verbalizer — the compact DSL and delta rendering, ported
 * from spike 006's verbalize.mjs (canonicalize/toCompactDsl) and run.mjs
 * lines 59-67 (renderDeltaContext).
 *
 * See the header line emitted by toCompactDsl() below for the exact grammar.
 *
 * Do not add a JSON dump format here. CONTEXT.md's locked decision forbids
 * raw JSON in LLM context (measured 2.9x token cost); `history.ts` in plan 05
 * uses JSON.stringify(canonicalize(...)) for SNAPSHOTS only, a different
 * consumer.
 */

// Canonical ordering rule: sort by logical string id. Entity insertion order
// and miniplex's numeric entity ids are NOT stable across churn — always
// return a COPY, never sort in place.
export function canonicalize<T extends { id: string }>(views: T[]): T[] {
  return [...views].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
}

export function toCompactDsl(views: CanvasView[]): string {
  const rows = canonicalize(views);
  const groups = new Map<string, CanvasView[]>();
  for (const v of rows) {
    if (!groups.has(v.kind)) groups.set(v.kind, []);
    groups.get(v.kind)!.push(v);
  }

  const lines = [
    '# pipeline_state — line format: <id> "<label>" <status>[/<lifecycle>][ detail=<detail>][ latency=<ms>][ creds:<c1,c2>][ flags:<f1,f2>]',
  ];

  for (const kind of [...groups.keys()].sort()) {
    lines.push(`[${kind}]`);
    for (const v of groups.get(kind)!) {
      const label = v.label.replace(/"/g, '');
      let line = `${v.id} "${label}" ${v.status}`;
      if (v.lifecycle) line += `/${v.lifecycle}`;
      if (v.detail) line += ` detail=${v.detail}`;
      if (v.latency !== null) line += ` latency=${Math.round(v.latency)}`;
      if (v.creds.length) line += ` creds:${v.creds.join(',')}`;
      if (v.flags.length) line += ` flags:${v.flags.join(',')}`;
      lines.push(line);
    }
  }

  return lines.join('\n');
}

export interface DeltaResult {
  text: string;
  changed: CanvasView[];
  removed: string[];
}

export function toDelta(
  dirty: Set<string>,
  removedIds: Set<string>,
  viewOf: (id: string) => CanvasView | null,
  version: number
): DeltaResult {
  const changed = [...dirty]
    .map((id) => viewOf(id))
    .filter((v): v is CanvasView => v !== null);

  const lines = [`# pipeline_state DELTA since v${version} — unchanged entities omitted`];

  if (removedIds.size) {
    lines.push(`removed: ${[...removedIds].sort().join(',')}`);
  }

  if (changed.length) {
    // Drop the verbalizer's own header line — the delta header above replaces it.
    lines.push(toCompactDsl(changed).split('\n').slice(1).join('\n'));
  } else if (!removedIds.size) {
    lines.push('(no changes)');
  }

  return { text: lines.join('\n'), changed, removed: [...removedIds] };
}
