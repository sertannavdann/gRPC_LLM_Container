// Sensitivity: delta savings as a function of world size at a FIXED absolute churn rate
// (the realistic case — SSE ticks touch a handful of entities regardless of world size).

import { encode } from "gpt-tokenizer";
import { World } from "miniplex";
import { makeStressFixture } from "./fixture.mjs";
import { FORMATS, toCompactDsl } from "./verbalize.mjs";
import { makeChurnScript } from "./churn.mjs";

for (const N of [26, 100, 400]) {
  const fixture = makeStressFixture(N);
  const world = new World();
  const byId = new Map();
  const dirty = new Set();
  const removedIds = new Set();
  const add = (rec) => { const e = world.add({ ...rec, credentials: [...rec.credentials] }); byId.set(rec.id, e); dirty.add(rec.id); removedIds.delete(rec.id); };
  const remove = (id) => { const e = byId.get(id); if (!e) return; world.remove(e); byId.delete(id); dirty.delete(id); removedIds.add(id); };
  const mutate = (id, patch) => { const e = byId.get(id); if (!e) return; Object.assign(e, patch); dirty.add(id); };
  const views = () => [...world.entities].map((e) => ({ ...e, credentials: [...e.credentials] }));

  fixture.forEach(add);
  dirty.clear();
  const script = makeChurnScript(fixture, 40, 1337);

  let full = 0, delta = 0, invocations = 0;
  for (let tick = 0; tick < script.length; tick++) {
    for (const op of script[tick]) {
      if (op.op === "metrics") mutate(op.id, { cpu: op.cpu, mem: op.mem });
      else if (op.op === "status") mutate(op.id, { status: op.value });
      else if (op.op === "remove") remove(op.id);
      else if (op.op === "add") add(op.rec);
    }
    if ((tick + 1) % 5 === 0) {
      full += encode(FORMATS["compact-dsl"](views())).length;
      const changed = [...dirty].map((id) => byId.get(id)).filter(Boolean).map((e) => ({ ...e, credentials: [...e.credentials] }));
      const lines = [`# DELTA`];
      if (removedIds.size) lines.push(`removed: ${[...removedIds].sort().join(",")}`);
      if (changed.length) lines.push(toCompactDsl(changed));
      delta += encode(lines.join("\n")).length;
      invocations++;
      dirty.clear(); removedIds.clear();
    }
  }
  console.log(
    `N=${String(N).padStart(4)}: full=${String(full).padStart(6)} tok, delta=${String(delta).padStart(5)} tok ` +
    `→ ${((1 - delta / full) * 100).toFixed(1)}% saved (${invocations} invocations, fixed ~3-5 entities churned/tick)`
  );
}
