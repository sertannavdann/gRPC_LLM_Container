/**
 * Finance Page
 * 
 * Embeds the interactive Chart.js finance dashboard
 * from the dashboard_service (port 8001).
 */
'use client';

import React, { useState } from 'react';
import { ExternalLink, RefreshCw } from 'lucide-react';

const DASHBOARD_URL = typeof window !== 'undefined'
  ? `${window.location.protocol}//${window.location.hostname}:8001`
  : 'http://localhost:8001';

export default function FinancePage() {
  const [iframeKey, setIframeKey] = useState(0);

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-card/60 flex-shrink-0">
        <h2 className="text-sm font-medium text-muted-foreground">
          Finance Dashboard
        </h2>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setIframeKey(k => k + 1)}
            className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            title="Refresh"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <a
            href={DASHBOARD_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 px-2 py-1 text-xs rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          >
            Open in new tab <ExternalLink className="w-3 h-3" />
          </a>
        </div>
      </div>

      {/* Iframe */}
      <iframe
        key={iframeKey}
        src={DASHBOARD_URL}
        className="flex-1 w-full border-0"
        title="Finance Dashboard"
        allow="clipboard-read; clipboard-write"
      />
    </div>
  );
}
