// Fairness probes for the 005 head-to-head:
// A) Where does bitECS's SoA grain actually win? Numeric-only workload at large N,
//    bitECS SoA serializer vs JSON.stringify of equivalent plain objects.
// B) Rewind semantics: restore an OLD snapshot into the SAME (drifted) world — does the
//    snapshot deserializer remove entities created after the snapshot? (008 preview.)

import { createWorld, addEntity, addComponent, query } from "bitecs";
import {
  createSnapshotSerializer, createSnapshotDeserializer,
  createSoASerializer, createSoADeserializer, f32, str,
} from "bitecs/serialization";

const log = (...a) => console.log(...a);
function bench(label, fn, iters) {
  fn(); fn();
  const t0 = performance.now();
  for (let i = 0; i < iters; i++) fn();
  const ms = (performance.now() - t0) / iters;
  log(`[bench] ${label}: ${ms.toFixed(4)} ms/op`);
  return ms;
}

// ---------- Probe A: numeric-only, large N ----------
for (const N of [5000, 50000]) {
  log(`\n--- numeric-only workload, N=${N} ---`);
  // bitECS: pure SoA, no strings, SoA serializer over eids.
  const Position = { x: f32([]), y: f32([]) };
  const Velocity = { vx: f32([]), vy: f32([]) };
  const Health = { value: f32([]) };
  const comps = [Position, Velocity, Health];
  const world = createWorld();
  const eids = [];
  for (let i = 0; i < N; i++) {
    const eid = addEntity(world);
    for (const c of comps) addComponent(world, eid, c);
    Position.x[eid] = i * 1.5; Position.y[eid] = i * 2.5;
    Velocity.vx[eid] = i % 10; Velocity.vy[eid] = i % 7;
    Health.value[eid] = i % 100;
    eids.push(eid);
  }
  const soaSerialize = createSoASerializer(comps, { buffer: new ArrayBuffer(1 << 24) });
  bench(`bitECS SoA serialize (${N})`, () => soaSerialize(eids), 50);

  // plain objects: same data as AoS objects, JSON.stringify.
  const objs = [];
  for (let i = 0; i < N; i++) {
    objs.push({ x: i * 1.5, y: i * 2.5, vx: i % 10, vy: i % 7, health: i % 100 });
  }
  bench(`JSON.stringify plain objects (${N})`, () => JSON.stringify(objs), 50);
}

// ---------- Probe B: rewind into a drifted world ----------
{
  log(`\n--- rewind semantics: restore old snapshot into SAME drifted world ---`);
  const Ident = { id: str([]) };
  const Metrics = { cpu: f32([]) };
  const comps = [Ident, Metrics];
  const world = createWorld();

  const e1 = addEntity(world);
  addComponent(world, e1, Ident); addComponent(world, e1, Metrics);
  Ident.id[e1] = "alpha"; Metrics.cpu[e1] = 10;

  const serialize = createSnapshotSerializer(world, comps, new ArrayBuffer(1 << 20));
  const deserialize = createSnapshotDeserializer(world, comps);
  const snapshot = serialize();

  // Drift: mutate alpha AND add a new entity afterwards.
  Metrics.cpu[e1] = 99;
  const e2 = addEntity(world);
  addComponent(world, e2, Ident); addComponent(world, e2, Metrics);
  Ident.id[e2] = "beta-added-after-snapshot"; Metrics.cpu[e2] = 55;

  deserialize(snapshot);

  const survivors = query(world, [Ident]).length ?? [...query(world, [Ident])].length;
  const alphaCpu = Metrics.cpu[e1];
  const betaPresent = [...query(world, [Ident])].some((eid) => Ident.id[eid] === "beta-added-after-snapshot");
  log(`entities after restore: ${[...query(world, [Ident])].length}`);
  log(`alpha cpu restored to 10: ${alphaCpu === 10 ? "OK" : `NO (${alphaCpu})`}`);
  log(`post-snapshot entity still present: ${betaPresent ? "YES — restore does NOT delete drifted entities (gotcha for rewind)" : "no — full rewind"}`);
}
