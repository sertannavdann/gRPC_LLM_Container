/**
 * Monitoring Page
 * 
 * Embeds Grafana dashboards for observability.
 * Grafana runs on port 3001 with provisioned dashboards.
 */
'use client';

import React, { useState } from 'react';
import { ExternalLink, RefreshCw, BarChart3 } from 'lucide-react';

const GRAFANA_URL = typeof window !== 'undefined'
  ? `${window.location.protocol}//${window.location.hostname}:3001`
  : 'http://localhost:3001';

const PROMETHEUS_URL = typeof window !== 'undefined'
  ? `${window.location.protocol}//${window.location.hostname}:9090`
  : 'http://localhost:9090';

const DASHBOARDS = [
  { label: 'Overview', path: '/d/grpc-llm-overview/grpc-llm-overview' },
  { label: 'Service Health', path: '/d/service-health/service-health' },
  { label: 'Provider Comparison', path: '/d/provider-comparison/provider-comparison' },
  { label: 'Tool Execution', path: '/d/tool-execution/tool-execution' },
] as const;

export default function MonitoringPage() {
  const [activeDashboard, setActiveDashboard] = useState<string>(DASHBOARDS[0].path);
  const [iframeKey, setIframeKey] = useState(0);

  const iframeSrc = `${GRAFANA_URL}${activeDashboard}?orgId=1&kiosk`;

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-card/60 flex-shrink-0">
        <div className="flex items-center gap-3">
          <BarChart3 className="w-4 h-4 text-orange-400" />
          <div className="flex items-center gap-1 bg-muted rounded-lg p-0.5">
            {DASHBOARDS.map(({ label, path }) => (
              <button
                key={path}
                onClick={() => { setActiveDashboard(path); setIframeKey(k => k + 1); }}
                className={`px-2.5 py-1 text-xs rounded-md transition-colors ${
                  activeDashboard === path
                    ? 'bg-primary text-primary-foreground font-medium'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setIframeKey(k => k + 1)}
            className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            title="Refresh"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <a
            href={GRAFANA_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 px-2 py-1 text-xs rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          >
            Grafana <ExternalLink className="w-3 h-3" />
          </a>
          <a
            href={PROMETHEUS_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 px-2 py-1 text-xs rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          >
            Prometheus <ExternalLink className="w-3 h-3" />
          </a>
        </div>
      </div>

      {/* Grafana iframe */}
      <iframe
        key={iframeKey}
        src={iframeSrc}
        className="flex-1 w-full border-0"
        title="Grafana Dashboard"
      />
    </div>
  );
}
