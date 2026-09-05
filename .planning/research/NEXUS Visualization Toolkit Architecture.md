# NEXUS Phase 6 Visualization Toolkit: Statechart-Driven Architecture with Modular Library Selection

## 1. Toolkit Selection Rationale

The recommended toolkit consists of four libraries that together cover every visualization requirement in Phase 6 while remaining entirely within the Next.js + TypeScript ecosystem. Each library handles a distinct concern with no overlap:

| Library | Version | Role | Bundle (gzip) | Phase 6 Plans |
|---|---|---|---|---|
| **XState** | v5 | Statechart state management (Harel formalism) | ~12 KB | All pages — state control |
| **React Flow** | v12 (xyflow) | Node-based interactive graphs | ~60 KB | 06-04 Monitoring topology, Pipeline |
| **Recharts** | v2.15+ | SVG charts (line, bar, donut, area) | ~40 KB | 06-03 Finance charts, 06-04 Latency |
| **Framer Motion** | v11+ | State transition animations | ~32 KB | All pages — animated transitions |

**Total additional bundle: ~144 KB gzip** — compared to the 1.1–2.5 MB minimum of Flutter Web. React Flow is already a NEXUS dependency, so the effective new addition is ~84 KB.[^1]

***

## 2. XState v5: Statechart Engine for Page State Control

### 2.1 Why XState for NEXUS

XState v5 implements Harel statecharts as executable TypeScript. It provides:[^2]

- **Parallel (orthogonal) state regions** — model independent concerns (data source status, auth state, capability freshness) without combinatorial explosion[^3]
- **Guards** — conditional transitions based on CapabilityEnvelope data (adapter locked? provider degraded?)[^4]
- **Invoked actors** — manage async operations (ETag polling, connection tests) as first-class citizens within the state machine[^5][^6]
- **Stately Studio visualizer** — visual debugging and design of statecharts at [state.new](https://state.new)[^2]
- **Zero dependencies**, works with `@xstate/react` hooks (`useMachine`, `useActor`)[^7]
- **Actor model** — each page's state machine is an independent actor that communicates via events, matching your microservice event-driven architecture[^2]

### 2.2 Root Application Statechart

The top-level NEXUS UI machine manages cross-cutting concerns as parallel regions:

```typescript
import { setup, assign, fromPromise } from 'xstate';

export const nexusAppMachine = setup({
  types: {
    context: {} as {
      envelope: CapabilityEnvelope | null;
      etag: string | null;
      error: NexusErrorType | null;
      userPrefs: UserPreferences | null;
    },
    events: {} as
      | { type: 'ENVELOPE_LOADED'; data: CapabilityEnvelope; etag: string }
      | { type: 'ENVELOPE_NOT_MODIFIED' }
      | { type: 'ENVELOPE_ERROR'; error: NexusErrorType }
      | { type: 'CAPABILITY_REFRESH_REQUESTED' }
      | { type: 'AUTH_EXPIRED' }
      | { type: 'PREFS_LOADED'; prefs: UserPreferences }
  },
  guards: {
    hasLiveAdapter: ({ context }) =>
      context.envelope?.adapters.some(a => !a.locked) ?? false,
    allAdaptersLocked: ({ context }) =>
      context.envelope?.adapters.every(a => a.locked) ?? true,
    isRetryableError: ({ context }) =>
      context.error === 'TIMEOUT' || context.error === 'DEGRADED_PROVIDER',
  },
  actors: {
    pollCapabilities: fromPromise(async ({ input }) => {
      return adminClient.getCapabilities(input.etag);
    }),
    pollConfigVersion: fromPromise(async ({ input }) => {
      return adminClient.getConfigVersion();
    }),
  },
}).createMachine({
  id: 'nexus-app',
  type: 'parallel',
  context: { envelope: null, etag: null, error: null, userPrefs: null },

  states: {
    // Region 1: Capability Data Lifecycle
    capability: {
      initial: 'loading',
      states: {
        loading: {
          invoke: {
            src: 'pollCapabilities',
            input: ({ context }) => ({ etag: context.etag }),
            onDone: {
              target: 'current',
              actions: assign({
                envelope: ({ event }) => event.output.data,
                etag: ({ event }) => event.output.etag,
                error: null,
              }),
            },
            onError: { target: 'error', actions: assign({ error: /* classify */ }) },
          },
        },
        current: {
          after: { 30000: 'polling' }, // 30s ETag poll
          on: { CAPABILITY_REFRESH_REQUESTED: 'loading' },
        },
        polling: {
          invoke: {
            src: 'pollConfigVersion',
            onDone: [
              { guard: 'etagChanged', target: 'loading' },
              { target: 'current' },
            ],
          },
        },
        error: {
          on: {
            CAPABILITY_REFRESH_REQUESTED: 'loading',
          },
          after: {
            5000: { target: 'loading', guard: 'isRetryableError' },
          },
        },
      },
    },

    // Region 2: Data Source Status (orthogonal)
    dataSource: {
      initial: 'unknown',
      states: {
        unknown: { always: [
          { guard: 'hasLiveAdapter', target: 'live' },
          { guard: 'allAdaptersLocked', target: 'mock' },
        ]},
        live: { on: { ENVELOPE_LOADED: [
          { guard: 'allAdaptersLocked', target: 'mock' },
        ]}},
        mock: { on: { ENVELOPE_LOADED: [
          { guard: 'hasLiveAdapter', target: 'live' },
        ]}},
        offline: { on: { ENVELOPE_LOADED: 'live' }},
      },
    },

    // Region 3: Auth Status (orthogonal)
    auth: {
      initial: 'authenticated',
      states: {
        authenticated: { on: { AUTH_EXPIRED: 'unauthenticated' }},
        unauthenticated: {},
      },
    },
  },
});
```

This single machine replaces scattered `useState` + `useEffect` patterns across pages with a deterministic, visualizable state model.[^8][^7]

### 2.3 Finance Page Machine (06-03)

Maps directly to the locked/unlocked gating in your 06-03-PLAN.md:

```typescript
export const financePageMachine = setup({
  guards: {
    financeAdapterLocked: ({ context }) =>
      context.envelope?.adapters
        .find(a => a.category === 'finance')?.locked ?? true,
  },
  actors: {
    testConnection: fromPromise(async ({ input }) => {
      return fetch('/api/adapters', { method: 'POST', body: JSON.stringify(input) });
    }),
    fetchFinanceData: fromPromise(async () => {
      return fetch('/api/finance').then(r => r.json());
    }),
  },
}).createMachine({
  id: 'finance-page',
  initial: 'checking',
  states: {
    checking: {
      always: [
        { guard: 'financeAdapterLocked', target: 'locked' },
        { target: 'unlocked' },
      ],
    },
    locked: {
      initial: 'idle',
      states: {
        idle: { on: { SUBMIT_CREDENTIALS: 'testing' }},
        testing: {
          invoke: {
            src: 'testConnection',
            onDone: 'succeeded',
            onError: 'failed',
          },
        },
        failed: { on: { SUBMIT_CREDENTIALS: 'testing', DISMISS: 'idle' }},
        succeeded: { type: 'final' }, // triggers parent onDone
      },
      onDone: 'unlocked', // transition when testConnection succeeds
    },
    unlocked: {
      initial: 'loading',
      states: {
        loading: {
          invoke: {
            src: 'fetchFinanceData',
            onDone: { target: 'loaded', actions: assign({ transactions: /* ... */ }) },
            onError: 'error',
          },
        },
        loaded: {
          on: { REFRESH: 'loading' },
        },
        error: {
          on: { RETRY: 'loading' },
        },
      },
    },
  },
});
```

### 2.4 Monitoring Page Machine (06-04)

```typescript
export const monitoringPageMachine = setup({
  actors: {
    fetchFeatureHealth: fromPromise(async () =>
      adminClient.getFeatureHealth()
    ),
    fetchLatencySnapshot: fromPromise(async () =>
      fetch('/api/monitoring/latency').then(r => r.json())
    ),
  },
}).createMachine({
  id: 'monitoring',
  type: 'parallel',
  states: {
    health: {
      initial: 'loading',
      states: {
        loading: {
          invoke: {
            src: 'fetchFeatureHealth',
            onDone: { target: 'loaded', actions: assign({ features: /* ... */ }) },
            onError: 'error',
          },
        },
        loaded: { after: { 30000: 'loading' } }, // auto-refresh
        error: { after: { 5000: 'loading' } },   // auto-retry
      },
    },
    latency: {
      initial: 'loading',
      states: {
        loading: {
          invoke: {
            src: 'fetchLatencySnapshot',
            onDone: { target: 'loaded', actions: assign({ latencyData: /* ... */ }) },
            onError: 'error',
          },
        },
        loaded: { after: { 60000: 'loading' } }, // refresh every 60s
        error: { after: { 10000: 'loading' } },
      },
    },
    activeTab: {
      initial: 'overview',
      states: {
        overview: { on: { TAB_MODULES: 'modules', TAB_ALERTS: 'alerts' }},
        modules: { on: { TAB_OVERVIEW: 'overview', TAB_ALERTS: 'alerts' }},
        alerts: { on: { TAB_OVERVIEW: 'overview', TAB_MODULES: 'modules' }},
      },
    },
  },
});
```

***

## 3. React Flow v12: Service Topology and Pipeline Visualization

### 3.1 React Flow v12 Capabilities

React Flow v12 (released February 2026 as `@xyflow/react`) provides:[^9][^10]

- **Server-side rendering** support — compatible with Next.js 14 SSR[^9]
- **Framework-agnostic core** (`@xyflow/system`) — shared internals with Svelte Flow[^10]
- **Custom nodes with full React rendering** — embed shadcn/ui Cards, Badges, and charts inside nodes[^11][^12]
- **Viewport-optimized rendering** — only visible nodes render, handling hundreds of nodes efficiently[^13]
- **Built-in Minimap, Controls, Background** components[^13]
- **Dark mode support** — native theming[^9]
- **`onBeforeDelete` handler** — validation hooks for node/edge operations[^9]

### 3.2 Service Topology Graph (Monitoring Page — 06-04)

Custom React Flow nodes map directly to your CapabilityEnvelope's `features` array:

```typescript
import { ReactFlow, Handle, Position, Background, MiniMap } from '@xyflow/react';
import { Badge } from '@/components/ui/badge';
import { motion } from 'framer-motion';

// Custom node that renders inside React Flow
function ServiceNode({ data }: { data: ServiceNodeData }) {
  const statusColor = {
    HEALTHY: 'bg-green-500',
    DEGRADED: 'bg-amber-500',
    UNAVAILABLE: 'bg-red-500',
    UNKNOWN: 'bg-gray-400',
  }[data.status];

  return (
    <motion.div
      className="px-4 py-3 border rounded-lg bg-card shadow-sm"
      animate={{ scale: data.status === 'DEGRADED' ? [1, 1.02, 1] : 1 }}
      transition={{ repeat: Infinity, duration: 2 }}
    >
      <Handle type="target" position={Position.Top} />
      <div className="flex items-center gap-2">
        <motion.div
          className={`w-3 h-3 rounded-full ${statusColor}`}
          animate={{ opacity: [1, 0.4, 1] }}
          transition={{ repeat: Infinity, duration: 1.5 }}
        />
        <span className="font-medium text-sm">{data.name}</span>
      </div>
      {data.p99 && (
        <Badge variant={data.p99 > 500 ? 'destructive' : 'secondary'}>
          P99: {data.p99}ms
        </Badge>
      )}
      <Handle type="source" position={Position.Bottom} />
    </motion.div>
  );
}

// Transform CapabilityEnvelope → React Flow nodes
function envelopeToTopology(envelope: CapabilityEnvelope, latency: LatencySnapshot) {
  const services = [
    { id: 'orchestrator', name: 'Orchestrator', x: 300, y: 0 },
    { id: 'llm-gateway', name: 'LLM Gateway', x: 100, y: 150 },
    { id: 'sandbox', name: 'Sandbox', x: 300, y: 150 },
    { id: 'chromadb', name: 'ChromaDB', x: 500, y: 150 },
    { id: 'ui', name: 'UI Service', x: 300, y: 300 },
    { id: 'dashboard', name: 'Dashboard', x: 100, y: 300 },
    { id: 'bridge', name: 'Bridge', x: 500, y: 300 },
  ];

  const nodes = services.map(s => ({
    id: s.id,
    type: 'serviceNode',
    position: { x: s.x, y: s.y },
    data: {
      name: s.name,
      status: envelope.features.find(f => f.feature === s.id)?.status ?? 'UNKNOWN',
      p99: latency[s.id]?.p99 ?? null,
      degradedReasons: envelope.features.find(f => f.feature === s.id)?.degraded_reasons ?? [],
    },
  }));

  const edges = [
    { id: 'e-orch-llm', source: 'orchestrator', target: 'llm-gateway', animated: true },
    { id: 'e-orch-sand', source: 'orchestrator', target: 'sandbox', animated: true },
    { id: 'e-orch-chroma', source: 'orchestrator', target: 'chromadb' },
    { id: 'e-ui-orch', source: 'ui', target: 'orchestrator', animated: true },
    { id: 'e-dash-orch', source: 'dashboard', target: 'orchestrator' },
    { id: 'e-bridge-orch', source: 'bridge', target: 'orchestrator' },
  ];

  return { nodes, edges };
}
```

### 3.3 Pipeline Stage Flow (Build Runs — 06-04)

React Flow also renders the build pipeline `scaffold → implement → test → repair` from agent run data:

```typescript
function PipelineStageNode({ data }: { data: PipelineStageData }) {
  const stageColors = {
    scaffold: 'border-blue-500',
    implement: 'border-purple-500',
    test: 'border-amber-500',
    repair: 'border-red-500',
  };

  return (
    <motion.div
      className={`px-3 py-2 border-2 rounded-md ${stageColors[data.stage]}`}
      animate={data.status === 'in-progress' ? { borderColor: ['#3b82f6', '#8b5cf6', '#3b82f6'] } : {}}
      transition={{ repeat: Infinity, duration: 2 }}
    >
      <Handle type="target" position={Position.Left} />
      <div className="text-xs font-mono">{data.stage}</div>
      <div className="text-xs text-muted-foreground">
        Attempt {data.attempt}/10
      </div>
      <Handle type="source" position={Position.Right} />
    </motion.div>
  );
}
```

***

## 4. Recharts: Financial Data and Latency Visualization

### 4.1 Finance Page Charts (06-03)

Recharts provides the `ResponsiveContainer` component that automatically adjusts chart dimensions using ResizeObserver, with SSR compatibility via `initialDimension` props:[^14][^15]

```typescript
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, PieChart, Pie, Cell
} from 'recharts';

// SpendingChart — line chart for monthly spending trend
export function SpendingChart({ data }: { data: MonthlySpend[] }) {
  return (
    <ResponsiveContainer width="100%" height={300} initialDimension={{ width: 400, height: 300 }}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
        <XAxis dataKey="month" className="text-xs" />
        <YAxis className="text-xs" />
        <Tooltip />
        <Line type="monotone" dataKey="amount" stroke="hsl(var(--primary))" strokeWidth={2} />
      </LineChart>
    </ResponsiveContainer>
  );
}

// CategoryBreakdown — donut chart for spend by category
export function CategoryBreakdown({ data }: { data: CategorySpend[] }) {
  const COLORS = ['#3b82f6', '#ef4444', '#22c55e', '#f59e0b', '#8b5cf6', '#ec4899'];
  return (
    <ResponsiveContainer width="100%" height={250}>
      <PieChart>
        <Pie data={data} dataKey="amount" nameKey="category" innerRadius={60} outerRadius={100}>
          {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
        </Pie>
        <Tooltip />
      </PieChart>
    </ResponsiveContainer>
  );
}
```

### 4.2 Latency Percentile Charts (Monitoring — 06-04)

```typescript
import { BarChart, Bar, ReferenceLine } from 'recharts';

export function LatencyChart({ data }: { data: ServiceLatency[] }) {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="service" />
        <YAxis label={{ value: 'ms', position: 'insideLeft' }} />
        <Tooltip />
        <Bar dataKey="p50" fill="#22c55e" name="P50" />
        <Bar dataKey="p95" fill="#f59e0b" name="P95" />
        <Bar dataKey="p99" fill="#ef4444" name="P99" />
        <ReferenceLine y={500} stroke="#ef4444" strokeDasharray="5 5" label="P99 Target" />
      </BarChart>
    </ResponsiveContainer>
  );
}
```

***

## 5. Framer Motion: State Transition Animations

Framer Motion provides declarative animations that respond to XState state changes without managing animation state manually:[^16][^17]

```typescript
import { motion, AnimatePresence } from 'framer-motion';

// Animated data source indicator (Dashboard — 06-02)
function DataSourceIndicator({ status }: { status: 'live' | 'mock' | 'offline' }) {
  const configs = {
    live:    { color: 'bg-green-500', label: 'Live', pulse: true },
    mock:    { color: 'bg-amber-500', label: 'Mock', pulse: false },
    offline: { color: 'bg-red-500',   label: 'Offline', pulse: false },
  };
  const cfg = configs[status];

  return (
    <motion.div
      className="flex items-center gap-2 px-3 py-1 rounded-full bg-muted"
      layout
      key={status}
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.3 }}
    >
      <motion.div
        className={`w-2 h-2 rounded-full ${cfg.color}`}
        animate={cfg.pulse ? { scale: [1, 1.4, 1], opacity: [1, 0.5, 1] } : {}}
        transition={{ repeat: Infinity, duration: 1.5 }}
      />
      <span className="text-xs font-medium">{cfg.label}</span>
    </motion.div>
  );
}

// Animated page transitions based on XState state
function PageContent({ state }: { state: StateFrom<typeof financePageMachine> }) {
  return (
    <AnimatePresence mode="wait">
      {state.matches('locked') && (
        <motion.div key="locked" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <UnlockForm />
        </motion.div>
      )}
      {state.matches('unlocked.loading') && (
        <motion.div key="loading" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
          <TimeoutSkeleton><TableSkeleton /></TimeoutSkeleton>
        </motion.div>
      )}
      {state.matches('unlocked.loaded') && (
        <motion.div key="loaded" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
          <TransactionTable /><SpendingChart />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
```

***

## 6. Complete Feature Matrix: Backend Component → Visualization Library

| Backend Component | CapabilityEnvelope Field | Visualization | Library | Plan |
|---|---|---|---|---|
| **Adapter connectivity** | `adapters[].locked` | Status badge + connect/disconnect | XState guards + shadcn Badge | 06-02 |
| **Adapter cards grid** | `adapters[]` | Responsive card grid | shadcn Card + Framer Motion layout | 06-02 |
| **Data source status** | Derived from `adapters[]` | Animated pill indicator | XState parallel region + Framer Motion | 06-02 |
| **ETag polling** | `config_version`, ETag header | Background state refresh | XState invoked actor (30s interval) | 06-01, 06-02 |
| **Feature health** | `features[].status` | Health cards + topology nodes | React Flow custom nodes | 06-04 |
| **P99/P95/P50 latency** | Latency snapshot endpoint | Grouped bar chart with target line | Recharts BarChart + ReferenceLine | 06-04 |
| **Service topology** | `features[]` + health check | Interactive node graph | React Flow v12 + custom ServiceNode | 06-04 |
| **Finance transactions** | `/api/finance` proxy | Sortable table | shadcn Table (native) | 06-03 |
| **Spending trend** | `/api/finance` aggregate | Line chart (6-month trend) | Recharts LineChart | 06-03 |
| **Category breakdown** | `/api/finance` categorized | Donut chart | Recharts PieChart | 06-03 |
| **Finance lock/unlock** | `adapters[].category='finance'` | Two-state page (form vs data) | XState hierarchical states | 06-03 |
| **Chat action cards** | `tool_calls` in orchestrator response | Inline confirmation cards | shadcn Card + Framer Motion | 06-03 |
| **Dashboard refresh trigger** | `capabilityRefreshTrigger` | Zustand → XState event bridge | XState `CAPABILITY_REFRESH_REQUESTED` | 06-03 |
| **Pipeline build runs** | Agent runs endpoint | Stage flow graph | React Flow + PipelineStageNode | 06-04 |
| **Error taxonomy** | HTTP status + response shape | DegradedBanner / EmptyState / Timeout | XState guards → component selection | 06-04 |
| **User preferences** | `/admin/user/prefs` | Persisted theme/layout/favorites | XState context + optimistic update | 06-04 |
| **Agent run history** | Orchestrator metrics endpoint | Sortable runs table | shadcn Table | 06-04 |
| **Grafana embed** | Docker Compose URLs | Tab-based iframe panels | shadcn Tabs (native) | 06-04 |

***

## 7. Integration Architecture

### 7.1 State Flow Diagram

```
CapabilityEnvelope (Backend REST)
        │
        ▼
┌──────────────────────┐
│  XState Root Machine  │ ← CAPABILITY_REFRESH_REQUESTED (from chat tool calls)
│  (nexusAppMachine)    │
│  ├── capability       │ → polls every 30s via invoked actor
│  ├── dataSource       │ → derives Live/Mock/Offline from envelope
│  └── auth             │ → tracks auth expiry
└──────────┬───────────┘
           │ state snapshots
           ▼
┌──────────────────────┐
│  Page-Level Machines  │
│  ├── financePageM.    │ → locked/unlocked hierarchy
│  ├── monitoringPageM. │ → parallel: health ∥ latency ∥ tabs
│  └── dashboardPageM.  │ → adapter actions, card grid state
└──────────┬───────────┘
           │ state.matches('...')
           ▼
┌──────────────────────────────────────┐
│  React Components (Next.js 14)       │
│  ├── React Flow    → topology/pipe   │
│  ├── Recharts      → charts          │
│  ├── Framer Motion → transitions     │
│  └── shadcn/ui     → cards/tables    │
└──────────────────────────────────────┘
```

### 7.2 Hook Integration Pattern

```typescript
// hooks/useNexusApp.ts — bridges XState to React components
import { useMachine } from '@xstate/react';
import { nexusAppMachine } from '@/machines/nexusApp';

export function useNexusApp() {
  const [state, send] = useMachine(nexusAppMachine);

  return {
    // Capability data
    envelope: state.context.envelope,
    isLoading: state.matches('capability.loading'),
    isError: state.matches('capability.error'),
    error: state.context.error,

    // Data source (orthogonal region)
    isLive: state.matches('dataSource.live'),
    isMock: state.matches('dataSource.mock'),
    isOffline: state.matches('dataSource.offline'),

    // Auth (orthogonal region)
    isAuthenticated: state.matches('auth.authenticated'),

    // Actions
    refresh: () => send({ type: 'CAPABILITY_REFRESH_REQUESTED' }),
  };
}
```

This replaces the `useCapabilities` hook defined in 06-02-PLAN.md with a statechart-backed equivalent that makes every state transition explicit and every error path deterministic.[^7]

### 7.3 Zustand Bridge for Cross-Page Events

Your existing `nexusStore.ts` bridges imperative triggers (chat tool call completion) into XState events:

```typescript
// stores/nexusStore.ts
import { useStore } from 'zustand';

export const useNexusStore = create((set) => ({
  xstateSend: null as ((event: any) => void) | null,
  setXStateSend: (send: (event: any) => void) => set({ xstateSend: send }),

  // Called after chat tool call completes
  triggerCapabilityRefresh: () => {
    const { xstateSend } = useNexusStore.getState();
    xstateSend?.({ type: 'CAPABILITY_REFRESH_REQUESTED' });
  },
}));
```

***

## 8. npm Package Manifest

```json
{
  "dependencies": {
    "@xyflow/react": "^12.0.0",
    "xstate": "^5.18.0",
    "@xstate/react": "^4.1.0",
    "recharts": "^2.15.0",
    "framer-motion": "^11.15.0"
  }
}
```

### Bundle Impact Analysis

| Package | Raw Size | Gzip | Tree-Shakeable | SSR Compatible |
|---|---|---|---|---|
| xstate | 45 KB | ~12 KB | Yes (setup API) | Yes[^7] |
| @xstate/react | 8 KB | ~3 KB | Yes | Yes |
| @xyflow/react | 180 KB | ~60 KB | Partial | Yes (v12)[^9] |
| recharts | 120 KB | ~40 KB | Partial[^14] | Yes (with initialDimension)[^15] |
| framer-motion | 100 KB | ~32 KB | Yes | Yes |
| **Total** | **~453 KB** | **~147 KB** | | |

With dynamic imports (`next/dynamic`), the actual initial page load adds only XState (~15 KB) since React Flow, Recharts, and Framer Motion load on-demand per page.[^18]

***

## 9. Compatibility with v0 + Cursor Workflow

| Workflow Step | Compatibility | Notes |
|---|---|---|
| **v0 Premium → visual shell** | ✅ Full | v0 generates shadcn/ui + Tailwind TSX. XState machines are separate TypeScript files. |
| **Cursor Pro → wiring** | ✅ Full | Cursor reads XState machine definitions, React Flow configs, Recharts data transforms. All TypeScript. |
| **shadcn/ui components** | ✅ Full | React Flow custom nodes render shadcn Cards/Badges inside. Recharts styled with CSS variables. |
| **Dark mode** | ✅ Full | React Flow v12 native dark mode. Recharts uses `hsl(var(--primary))`. Framer Motion animates CSS vars. |
| **Next.js 14 SSR** | ✅ Full | All libraries support SSR. XState machines hydrate on client. Recharts uses `initialDimension`.[^7][^9] |
| **ETag polling** | ✅ Replaced | XState invoked actor replaces `setInterval` with statechart-managed polling. Cleaner cleanup. |
| **Error taxonomy** | ✅ Enhanced | XState guards replace `if/else` chains with declarative transition conditions[^4]. |
| **P99 < 500ms target** | ✅ No conflict | ~147 KB gzip total, lazy-loaded per page. No game loop, no continuous rendering. |

***

## 10. Key References

1. **XState v5 Documentation** (2024–2026). "Actor-based state management & orchestration." Stately.ai. — Parallel states, guards, invoked services, TypeScript setup API.[^4][^3][^2]

2. **React Flow v12 Release** (2026). "Even More Features!" xyflow. — SSR support, dark mode, framework-agnostic core, `onBeforeDelete` handler.[^10][^9]

3. **React Flow Documentation** (2026). "Custom Nodes" and "API Reference." — Custom node rendering with handles, embedding React components inside nodes.[^12][^11]

4. **Recharts SSR Integration** (2025). "Recharts服务端渲染方案." — `ResponsiveContainer` SSR compatibility via `initialDimension`, ResizeObserver lifecycle.[^15][^14]

5. **Speakeasy** (2022). "Nivo vs Recharts." — Comparative analysis recommending Recharts for responsiveness and reliability.[^19]

6. **XState + Next.js Integration** (2024). "Integrating NextJS with XState." Restack. — `useMachine` hook patterns, dynamic imports for code splitting, visual workflow debugging.[^7]

7. **Maglione, S.** (2024). "State machines and Actors in XState v5." — Invoked actors for async operations, context initialization from input.[^5]

8. **React Flow Examples** (2026). "Animated layout transitions, custom shapes, data flow helpers." — Interactive patterns for service topology and pipeline visualization.[^20]

---

## References

1. [Flutter Web Is a Bad Idea | Suica's blog](https://suica.dev/en/blogs/fuck-off-flutter-web,-unless-you-slept-through-school,-you-know-flutter-web-is-a-bad-idea) - We can see that the performance on mobile platform is much better than Flutter Web, but it is still ...

2. [statelyai/xstate: Actor-based state management & ...](https://github.com/statelyai/xstate) - XState is a state management and orchestration solution for JavaScript and TypeScript apps. It has z...

3. [# Parallel State Nodes](https://xstate.js.org/docs/guides/parallel) - Documentation for XState: State Machines and Statecharts for the Modern Web

4. [Guards and TypeScript](https://stately.ai/docs/guards)

5. [State machines and Actors in XState v5](https://www.sandromaglione.com/articles/state-machines-and-actors-in-xstate-v5) - Learn how to implement a state machine using actors in XState v5, how to organize the code for conte...

6. [# Invoking Services](https://xstate.js.org/docs/guides/communication.html) - Documentation for XState: State Machines and Statecharts for the Modern Web

7. [Integrating NextJS with XState](https://www.restack.io/docs/nextjs-knowledge-nextjs-xstate-integration) - Explore how NextJS and XState work together for state management in modern web applications.

8. [XState in React: Look Ma, no useState or useEffect!](https://www.frontendundefined.com/posts/monthly/xstate-in-react/) - The React package for XState provides hooks for sending events to a state machine and reading its st...

9. [Even More Features!](https://xyflow.com/blog/react-flow-12-release) - A new React Flow major release version 12 with server side rendering, computing flows, dark mode, be...

10. [1. A New Npm Package Name](https://reactflow.dev/learn/troubleshooting/migrate-to-v12) - Use this guide to migrate from React Flow 11 to 12.

11. [API Reference](https://reactflow.dev/api-reference) - Within your custom nodes you can render everything you want. You can define multiple source and targ...

12. [Custom Nodes](https://reactflow.dev/learn/customization/custom-nodes) - A powerful feature of React Flow is the ability to create custom nodes. This gives you the flexibili...

13. [GitHub - Sebb77/react-flow: React library for building interactive node-based graphs | flow charts | diagrams](https://github.com/Sebb77/react-flow) - React library for building interactive node-based graphs | flow charts | diagrams - Sebb77/react-flo...

14. [Recharts服务端渲染方案：Next.js中集成Recharts - CSDN博客](https://blog.csdn.net/gitblog_01161/article/details/152031190) - 文章浏览阅读327次，点赞4次，收藏9次。在现代React应用开发中，服务端渲染(Server-Side Rendering, SSR)已成为提升首屏加载速度和搜索引擎优化(Search Engine...

15. [ResponsiveContainer - Recharts](https://recharts.github.io/en-US/api/ResponsiveContainer/) - Recharts - Re-designed charting library built with React and D3.

16. [How to animate on each state change using framer motion](https://stackoverflow.com/questions/69051279/how-to-animate-on-each-state-change-using-framer-motion) - I thought on ever render framer motion would re-do my animation because the inital is set to hide an...

17. [How to Animate A React Application With Framer Motion](https://coderpad.io/blog/development/how-to-animate-a-react-application-with-framer-motion/) - It allows you to add all forms of animations and transitions directly to Document Object Model (DOM)...

18. [Optimizing bundle size in Next.js 14](https://bytenote.net/article/216628131862151170) - <p>To optimize bundle size in Next.js 14, you can follow these strategies:</p> <ol> <li> <p>Tree Sha...

19. [Nivo vs Recharts - Which should you use? - Speakeasy](https://www.speakeasy.com/blog/nivo-vs-recharts) - Which React Charting Library should you use: Nivo or Recharts?

20. [Examples](https://reactflow.dev/examples) - Browse our examples for practical copy-paste solutions to common use cases with React Flow. Here you...

