// bitECS-native delta machinery probe for spike 006. Three questions:
//
// Q1: Does ObserverSerializer + SoA diff mode tell the APPLICATION which entities
//     changed (so it can verbalize a text delta for LLM context)? Or is the delta
//     opaque binary consumable only by the paired deserializer?
// Q2: Do binary deltas correctly sync a mirror world (the wire scenario they're
//     actually built for), and what do they cost in bytes vs full snapshots?
// Q3: Can set() + observe(onSet) — the 003b footgun turned into the required API —
//     serve as bitECS's native dirty-set choke point, and what does it cost in LOC?

import {
  createWorld, addEntity, addComponent, query, observe, onSet, set,
} from "bitecs";
import {
  createObserverSerializer, createObserverDeserializer,
  createSoASerializer, createSoADeserializer, f32, str,
} from "bitecs/serialization";

const log = (...a) => console.log(...a);

// Minimal 3-entity world: Ident(id str), Metrics(cpu f32).
function makeWorld() {
  const Ident = { id: str([]) };
  const Metrics = { cpu: f32([]) };
  const Networked = {};
  const world = createWorld();
  return { world, Ident, Metrics, Networked };
}

// ---------- Q1 + Q2: observer + diff SoA round trip into mirror ----------
{
  const src = makeWorld();
  const dst = makeWorld();
  const comps = (w) => [w.Ident, w.Metrics];

  const obsSer = createObserverSerializer(src.world, src.Networked, comps(src));
  const obsDes = createObserverDeserializer(dst.world, dst.Networked, comps(dst));
  const soaSer = createSoASerializer(comps(src), { diff: true, buffer: new ArrayBuffer(1 << 20) });
  const soaDes = createSoADeserializer(comps(dst), { diff: true });

  const eids = [];
  for (let i = 0; i < 3; i++) {
    const eid = addEntity(src.world);
    addComponent(src.world, eid, src.Networked);
    addComponent(src.world, eid, src.Ident);
    addComponent(src.world, eid, src.Metrics);
    src.Ident.id[eid] = `entity-${i}`;
    src.Metrics.cpu[eid] = i * 10;
    eids.push(eid);
  }

  // Initial sync (baseline).
  const obs0 = obsSer();
  const idMap = obsDes(obs0);
  const soa0 = soaSer(eids);
  soaDes(soa0, idMap);
  log(`[q2] baseline sync: observer packet ${obs0.byteLength} B, soa-diff packet ${soa0.byteLength} B`);

  // Mutate ONE entity, then produce delta packets.
  src.Metrics.cpu[eids[1]] = 99.5;
  const obs1 = obsSer();
  const soa1 = soaSer(eids); // diff mode: only changed values should be encoded
  log(`[q2] after 1 mutation: observer packet ${obs1.byteLength} B, soa-diff packet ${soa1.byteLength} B`);

  // Q1: can the APP learn which entities changed from these packets without a paired
  // deserializer? The packet is an ArrayBuffer with an internal format — inspecting the
  // API surface: serializer returns bytes only; no change-set accessor exists.
  log(`[q1] serializer return type: ArrayBuffer — no change-set/entity-list accessor on the API`);

  // Apply to mirror and verify the wire scenario works.
  const idMap1 = obsDes(obs1);
  soaDes(soa1, idMap1.size ? idMap1 : idMap);
  const mirrorEids = query(dst.world, [dst.Ident]);
  const cpuInMirror = [...mirrorEids].map((eid) => `${dst.Ident.id[eid]}=${dst.Metrics.cpu[eid]}`).join(", ");
  log(`[q2] mirror after delta apply: ${cpuInMirror}`);
}

// ---------- Q3: set() + observe(onSet) as native dirty tracking ----------
{
  const { world, Ident, Metrics } = makeWorld();
  const dirty = new Set();

  // Register onSet writers — REQUIRED for set() to do anything at all (003b finding).
  observe(world, onSet(Metrics), (eid, params) => {
    if (params?.cpu !== undefined) Metrics.cpu[eid] = params.cpu;
    dirty.add(Ident.id[eid]);
    return params;
  });

  const eid = addEntity(world);
  addComponent(world, eid, Ident);
  addComponent(world, eid, Metrics);
  Ident.id[eid] = "alpha";
  Metrics.cpu[eid] = 10;

  // Mutation through the choke point:
  addComponent(world, eid, set(Metrics, { cpu: 42 }));
  log(`[q3] set()+onSet dirty tracking: cpu=${Metrics.cpu[eid]} dirty=${JSON.stringify([...dirty])}`);
  log(`[q3] NOTE: direct array writes (Metrics.cpu[eid]=7) bypass the observer silently — the choke point is convention-enforced only, same as miniplex's mutate() helper`);
}
