// Shared fixture for spikes 005a/005b — MUST stay byte-identical in both packages.
// Deterministic synthetic pipeline world modeled on the real SSE pipeline-state shape
// (dashboard_service/pipeline_stream.py): services, modules, build stages.

export const KINDS = ["service", "module", "stage"];
export const STATUSES = ["unknown", "running", "degraded", "stopped", "building", "validating", "failed"];
export const LIFECYCLES = ["discovered", "installed", "enabled", "disabled", "error"];

// 26 entities: 7 services, 15 modules, 4 stages — the realistic "dozens" scale.
export function makeFixture() {
  const services = [
    ["svc-orchestrator", "Orchestrator", "running", 12.4, 342.5, 120, 80],
    ["svc-llm", "LLM Service", "running", 78.1, 4820.0, 320, 80],
    ["svc-dashboard", "Dashboard", "running", 3.2, 128.7, 520, 80],
    ["svc-chroma", "ChromaDB", "degraded", 22.9, 890.2, 120, 220],
    ["svc-bridge", "Bridge Service", "running", 1.1, 64.3, 320, 220],
    ["svc-sandbox", "Sandbox", "stopped", 0.0, 0.0, 520, 220],
    ["svc-ui", "UI Service", "running", 5.6, 210.9, 720, 80],
  ];
  const modules = [
    ["mod-weather-openweather", "OpenWeather Adapter", "running", "enabled", ["OPENWEATHER_API_KEY"]],
    ["mod-calendar-google", "Google Calendar Adapter", "running", "enabled", ["GOOGLE_OAUTH_TOKEN", "GOOGLE_REFRESH_TOKEN"]],
    ["mod-gaming-clashroyale", "Clash Royale Adapter", "degraded", "enabled", ["CLASH_BEARER_TOKEN"]],
    ["mod-finance-cibc", "CIBC CSV Adapter", "running", "enabled", []],
    ["mod-finance-categorizer", "Merchant Categorizer", "running", "enabled", []],
    ["mod-test-hello", "Hello Smoke Test", "stopped", "disabled", []],
    ["mod-showroom-metrics", "Metrics Demo", "running", "enabled", []],
    ["mod-knowledge-search", "Knowledge Search", "running", "enabled", ["CHROMA_HOST"]],
    ["mod-context-bridge", "Context Bridge", "running", "enabled", []],
    ["mod-notes-notion", "Notion Notes Adapter", "building", "installed", ["NOTION_API_KEY"]],
    ["mod-music-spotify", "Spotify Adapter", "validating", "installed", ["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"]],
    ["mod-fitness-strava", "Strava Adapter", "failed", "error", ["STRAVA_ACCESS_TOKEN"]],
    ["mod-mail-gmail", "Gmail Adapter", "running", "enabled", ["GMAIL_OAUTH_TOKEN"]],
    ["mod-tasks-todoist", "Todoist Adapter", "stopped", "disabled", ["TODOIST_API_KEY"]],
    ["mod-news-rss", "RSS News Adapter", "running", "enabled", []],
  ];
  const stages = [
    ["stage-build", "Build", "running"],
    ["stage-validate", "Validate", "running"],
    ["stage-install", "Install", "unknown"],
    ["stage-approve", "Approval Gate", "unknown"],
  ];

  const entities = [];
  for (const [id, label, status, cpu, mem, x, y] of services) {
    entities.push({ id, label, kind: "service", status, lifecycle: null, cpu, mem, x, y, credentials: [] });
  }
  modules.forEach(([id, label, status, lifecycle, credentials], i) => {
    entities.push({
      id, label, kind: "module", status, lifecycle,
      cpu: Math.round((i * 1.7 + 0.3) * 10) / 10,
      mem: Math.round((i * 23.5 + 12.0) * 10) / 10,
      x: 120 + (i % 5) * 150, y: 380 + Math.floor(i / 5) * 120,
      credentials,
    });
  });
  stages.forEach(([id, label, status], i) => {
    entities.push({
      id, label, kind: "stage", status, lifecycle: null,
      cpu: 0, mem: 0, x: 120 + i * 200, y: 740, credentials: [],
    });
  });
  return entities;
}

// Churn script for determinism testing: remove 3 logical entities, re-add them in a
// DIFFERENT order with identical values, and touch two mutations that are then reverted.
// After applying, the world's logical content is identical to the original fixture.
export const CHURN_REMOVE_IDS = ["mod-test-hello", "svc-sandbox", "mod-news-rss"];
export const CHURN_READD_ORDER = ["mod-news-rss", "mod-test-hello", "svc-sandbox"];

// Stress scale for benchmarks.
export function makeStressFixture(count = 5000) {
  const entities = [];
  for (let i = 0; i < count; i++) {
    const kind = KINDS[i % 3];
    entities.push({
      id: `${kind}-stress-${i}`,
      label: `Stress ${kind} #${i} with a plausibly long human label`,
      kind,
      status: STATUSES[i % STATUSES.length],
      lifecycle: kind === "module" ? LIFECYCLES[i % LIFECYCLES.length] : null,
      cpu: Math.round(((i * 7919) % 1000) / 10 * 10) / 10,
      mem: Math.round(((i * 104729) % 8000) * 10) / 10,
      x: (i * 37) % 1600,
      y: (i * 53) % 1200,
      credentials: kind === "module" && i % 4 === 0 ? [`KEY_A_${i}`, `KEY_B_${i}`] : [],
    });
  }
  return entities;
}
