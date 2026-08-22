// bitECS 0.4.0 world adapter for spike 005a.
//
// Representation choices under test:
// - Numeric fields in tagged SoA arrays (f32) — the library's native grain.
// - String fields in str([])-branded arrays; string lists in array(str) — the
//   serialization module's native string support (discovered in research; 003b assumed
//   hand-rolled interning would be required).
// - Status/kind/lifecycle as u8 enum codes + JS-side decode tables (the 003b pattern).
//
// Known 003b footgun honored: NO set() helper anywhere — addComponent(world, eid, C)
// plus direct array writes only.

import {
  createWorld, addEntity, removeEntity, addComponent, query,
} from "bitecs";
import {
  createSnapshotSerializer, createSnapshotDeserializer, f32, u8, str, array,
} from "bitecs/serialization";
import { KINDS, STATUSES, LIFECYCLES } from "./fixture.mjs";

const LIFECYCLE_NONE = 255;

export function createPipelineWorld() {
  const world = createWorld();
  // Fresh component stores per world so tests are isolated.
  const C = {
    Ident: { id: str([]), label: str([]) },
    Kind: { value: u8([]) },
    Status: { value: u8([]) },
    Lifecycle: { value: u8([]) },
    Metrics: { cpu: f32([]), mem: f32([]) },
    Position: { x: f32([]), y: f32([]) },
    Credentials: { list: array(str) },
  };
  const components = [C.Ident, C.Kind, C.Status, C.Lifecycle, C.Metrics, C.Position, C.Credentials];
  const byId = new Map(); // logical id -> eid

  function add(rec) {
    const eid = addEntity(world);
    for (const comp of components) addComponent(world, eid, comp);
    C.Ident.id[eid] = rec.id;
    C.Ident.label[eid] = rec.label;
    C.Kind.value[eid] = KINDS.indexOf(rec.kind);
    C.Status.value[eid] = STATUSES.indexOf(rec.status);
    C.Lifecycle.value[eid] = rec.lifecycle === null ? LIFECYCLE_NONE : LIFECYCLES.indexOf(rec.lifecycle);
    C.Metrics.cpu[eid] = rec.cpu;
    C.Metrics.mem[eid] = rec.mem;
    C.Position.x[eid] = rec.x;
    C.Position.y[eid] = rec.y;
    C.Credentials.list[eid] = [...rec.credentials];
    byId.set(rec.id, eid);
    return eid;
  }

  function remove(id) {
    const eid = byId.get(id);
    if (eid === undefined) return;
    removeEntity(world, eid);
    byId.delete(id);
  }

  // Read one entity back into a canonical plain view record.
  function view(eid) {
    // f32 storage rounds decimals; round to 1dp to recover fixture precision.
    const r1 = (n) => Math.round(n * 10) / 10;
    const lc = C.Lifecycle.value[eid];
    return {
      id: C.Ident.id[eid],
      label: C.Ident.label[eid],
      kind: KINDS[C.Kind.value[eid]],
      status: STATUSES[C.Status.value[eid]],
      lifecycle: lc === LIFECYCLE_NONE ? null : LIFECYCLES[lc],
      cpu: r1(C.Metrics.cpu[eid]),
      mem: r1(C.Metrics.mem[eid]),
      x: r1(C.Position.x[eid]),
      y: r1(C.Position.y[eid]),
      credentials: [...(C.Credentials.list[eid] ?? [])],
    };
  }

  function views() {
    return query(world, [C.Ident]).map ? [...query(world, [C.Ident])].map(view) : Array.from(query(world, [C.Ident]), view);
  }

  const serialize = createSnapshotSerializer(world, components, new ArrayBuffer(1 << 22)); // 4MB
  const deserialize = createSnapshotDeserializer(world, components);

  return { world, C, components, byId, add, remove, view, views, serialize, deserialize };
}

// Rough LOC of glue this adapter needed beyond what miniplex needs (measured in run.mjs
// by counting this file's lines; recorded for the head-to-head).
