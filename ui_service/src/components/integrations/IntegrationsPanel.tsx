/**
 * Integrations Panel
 *
 * Full-page configuration for adapter connections.
 * Shows each adapter with connection status, credential inputs,
 * and activate/deactivate toggles. Saves to .env and triggers
 * dashboard service restart.
 */
'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  Loader2,
  AlertCircle,
  Check,
  X,
  Eye,
  EyeOff,
  RefreshCw,
  Plug,
  Unplug,
  ChevronDown,
  ChevronRight,
  Shield,
  Zap,
} from 'lucide-react';

interface AuthField {
  key: string;
  label: string;
  placeholder: string;
  type: string;
  envVar: string;
}

interface AdapterInfo {
  platform: string;
  name: string;
  icon: string;
  connected: boolean;
  status: 'active' | 'available' | 'error';
  auth_type: 'api_key' | 'oauth2' | 'none';
  auth_fields: AuthField[];
}

interface CategoryInfo {
  category: string;
  icon: string;
  adapters: AdapterInfo[];
  connected_count: number;
}

interface AdaptersData {
  categories: CategoryInfo[];
  total_connected: number;
  total_available: number;
}

type ServiceStatus = 'idle' | 'restarting' | 'ready' | 'error';

export function IntegrationsPanel() {
  const [data, setData] = useState<AdaptersData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedAdapters, setExpandedAdapters] = useState<Set<string>>(new Set());
  const [credentials, setCredentials] = useState<Record<string, Record<string, string>>>({});
  const [savingAdapter, setSavingAdapter] = useState<string | null>(null);
  const [serviceStatus, setServiceStatus] = useState<ServiceStatus>('idle');
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [visibleFields, setVisibleFields] = useState<Set<string>>(new Set());

  const fetchAdapters = useCallback(async () => {
    try {
      const res = await fetch('/api/dashboard/adapters');
      if (!res.ok) throw new Error('Failed to fetch adapters');
      const result: AdaptersData = await res.json();
      setData(result);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAdapters();
  }, [fetchAdapters]);

  const toggleExpand = (key: string) => {
    setExpandedAdapters((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const toggleFieldVisibility = (fieldKey: string) => {
    setVisibleFields((prev) => {
      const next = new Set(prev);
      if (next.has(fieldKey)) next.delete(fieldKey);
      else next.add(fieldKey);
      return next;
    });
  };

  const updateCredential = (adapterKey: string, fieldKey: string, value: string) => {
    setCredentials((prev) => ({
      ...prev,
      [adapterKey]: { ...(prev[adapterKey] || {}), [fieldKey]: value },
    }));
  };

  const handleConnect = async (category: string, adapter: AdapterInfo) => {
    const adapterKey = `${category}-${adapter.platform}`;
    const creds = credentials[adapterKey] || {};

    // Validate required fields
    const missingFields = adapter.auth_fields
      .filter((f) => f.type === 'api_key' || f.type === 'oauth_token')
      .filter((f) => !creds[f.key]?.trim());

    if (missingFields.length > 0) {
      setError(`Missing required fields: ${missingFields.map((f) => f.label).join(', ')}`);
      return;
    }

    setSavingAdapter(adapterKey);
    setError(null);
    setSuccessMessage(null);

    try {
      const res = await fetch('/api/dashboard/adapters', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          category,
          platform: adapter.platform,
          action: 'connect',
          credentials: creds,
        }),
      });

      const result = await res.json();
      if (!res.ok) throw new Error(result.error || 'Failed to connect');

      // Clear credentials from local state
      setCredentials((prev) => {
        const next = { ...prev };
        delete next[adapterKey];
        return next;
      });

      setSuccessMessage(result.message);

      // Restart dashboard service if needed
      if (result.restartRequired) {
        await restartDashboard();
      }

      // Refresh adapter list
      await fetchAdapters();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSavingAdapter(null);
    }
  };

  const handleDisconnect = async (category: string, adapter: AdapterInfo) => {
    const adapterKey = `${category}-${adapter.platform}`;
    setSavingAdapter(adapterKey);
    setError(null);
    setSuccessMessage(null);

    try {
      const res = await fetch('/api/dashboard/adapters', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          category,
          platform: adapter.platform,
          action: 'disconnect',
        }),
      });

      const result = await res.json();
      if (!res.ok) throw new Error(result.error || 'Failed to disconnect');

      setSuccessMessage(result.message);
      await fetchAdapters();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSavingAdapter(null);
    }
  };

  const restartDashboard = async () => {
    setServiceStatus('restarting');
    try {
      // Attempt to restart via orchestrator API
      const res = await fetch('/api/orchestrator', { method: 'POST' });
      const result = await res.json();
      if (result.manualRequired) {
        setServiceStatus('error');
        setError('Auto-restart not available. Run: docker compose restart dashboard');
        return;
      }
      // Wait briefly for service to restart
      await new Promise((r) => setTimeout(r, 3000));
      setServiceStatus('ready');
    } catch {
      setServiceStatus('error');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full min-h-[400px] text-muted-foreground">
        <Loader2 className="w-6 h-6 animate-spin" />
      </div>
    );
  }

  const connectable = data?.categories.filter((c) =>
    c.adapters.some((a) => a.auth_type !== 'none')
  ) || [];
  const alwaysOn = data?.categories.filter((c) =>
    c.adapters.every((a) => a.auth_type === 'none')
  ) || [];

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-8">
      {/* Header */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Integrations</h1>
            <p className="text-sm text-muted-foreground mt-1">
              Connect external services to power your dashboard with real data.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 px-3 py-1.5 bg-muted rounded-lg text-xs text-muted-foreground">
              <Zap className="w-3.5 h-3.5" />
              {data?.total_connected || 0} / {data?.total_available || 0} active
            </div>
            <button
              onClick={() => { setLoading(true); fetchAdapters(); }}
              className="p-2 hover:bg-muted rounded-lg transition-colors text-muted-foreground hover:text-foreground"
              title="Refresh"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Status messages */}
      {error && (
        <div className="flex items-center gap-2 p-3 bg-destructive/10 border border-destructive/30 text-destructive rounded-lg text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
          <button onClick={() => setError(null)} className="ml-auto p-0.5 hover:bg-destructive/20 rounded">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {successMessage && (
        <div className="flex items-center gap-2 p-3 bg-green-500/10 border border-green-500/30 text-green-600 rounded-lg text-sm">
          <Check className="w-4 h-4 flex-shrink-0" />
          <span>{successMessage}</span>
          <button onClick={() => setSuccessMessage(null)} className="ml-auto p-0.5 hover:bg-green-500/20 rounded">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {serviceStatus === 'restarting' && (
        <div className="flex items-center gap-2 p-3 bg-blue-500/10 border border-blue-500/30 text-blue-500 rounded-lg text-sm">
          <RefreshCw className="w-4 h-4 animate-spin" />
          <span>Restarting dashboard service...</span>
        </div>
      )}

      {/* Connectable Adapters */}
      {connectable.length > 0 && (
        <section className="space-y-4">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            External Services
          </h2>
          <div className="space-y-3">
            {connectable.map((cat) =>
              cat.adapters
                .filter((a) => a.auth_type !== 'none')
                .map((adapter) => {
                  const adapterKey = `${cat.category}-${adapter.platform}`;
                  const isExpanded = expandedAdapters.has(adapterKey);
                  const isSaving = savingAdapter === adapterKey;
                  const creds = credentials[adapterKey] || {};

                  return (
                    <div
                      key={adapterKey}
                      className={`border rounded-xl overflow-hidden transition-all ${
                        adapter.connected
                          ? 'border-green-500/30 bg-green-500/5'
                          : 'border-border bg-card'
                      }`}
                    >
                      {/* Adapter header */}
                      <div
                        className="flex items-center justify-between px-5 py-4 cursor-pointer hover:bg-muted/30 transition-colors"
                        onClick={() => toggleExpand(adapterKey)}
                      >
                        <div className="flex items-center gap-4">
                          <span className="text-2xl">{adapter.icon}</span>
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-semibold">{adapter.name}</span>
                              <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground capitalize">
                                {cat.category}
                              </span>
                            </div>
                            <span className="text-xs text-muted-foreground">
                              {adapter.auth_type === 'oauth2' ? 'OAuth 2.0' : 'API Key'} authentication
                            </span>
                          </div>
                        </div>

                        <div className="flex items-center gap-3">
                          {adapter.connected ? (
                            <span className="flex items-center gap-1.5 text-xs font-medium text-green-500">
                              <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                              Connected
                            </span>
                          ) : (
                            <span className="text-xs text-muted-foreground">Not connected</span>
                          )}
                          {isExpanded ? (
                            <ChevronDown className="w-4 h-4 text-muted-foreground" />
                          ) : (
                            <ChevronRight className="w-4 h-4 text-muted-foreground" />
                          )}
                        </div>
                      </div>

                      {/* Expanded: credential fields */}
                      {isExpanded && (
                        <div className="px-5 pb-5 border-t border-border/50">
                          <div className="pt-4 space-y-4">
                            {/* Security notice */}
                            <div className="flex items-start gap-2 p-3 bg-muted/50 rounded-lg text-xs text-muted-foreground">
                              <Shield className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                              <span>
                                Credentials are stored in your local .env file and never transmitted externally.
                                {adapter.auth_type === 'oauth2' && ' For OAuth2, you need tokens from the Google Cloud Console.'}
                              </span>
                            </div>

                            {/* Credential fields */}
                            {adapter.auth_fields.map((field) => {
                              const fieldId = `${adapterKey}-${field.key}`;
                              const isSecret = field.type === 'api_key' || field.type === 'oauth_token';
                              const isVisible = visibleFields.has(fieldId);

                              return (
                                <div key={field.key} className="space-y-1.5">
                                  <label className="text-xs font-medium text-foreground/80">{field.label}</label>
                                  <div className="relative">
                                    <input
                                      type={isSecret && !isVisible ? 'password' : 'text'}
                                      value={creds[field.key] || ''}
                                      onChange={(e) => updateCredential(adapterKey, field.key, e.target.value)}
                                      placeholder={adapter.connected ? '(configured)' : field.placeholder}
                                      className="w-full px-3 py-2 text-sm rounded-lg border bg-background font-mono pr-10 focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none transition-all"
                                    />
                                    {isSecret && (
                                      <button
                                        type="button"
                                        onClick={() => toggleFieldVisibility(fieldId)}
                                        className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted-foreground hover:text-foreground"
                                      >
                                        {isVisible ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                                      </button>
                                    )}
                                  </div>
                                </div>
                              );
                            })}

                            {/* Action buttons */}
                            <div className="flex items-center gap-2 pt-2">
                              {adapter.connected ? (
                                <>
                                  <button
                                    onClick={() => handleConnect(cat.category, adapter)}
                                    disabled={isSaving}
                                    className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
                                  >
                                    {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                                    Update Credentials
                                  </button>
                                  <button
                                    onClick={() => handleDisconnect(cat.category, adapter)}
                                    disabled={isSaving}
                                    className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg border border-destructive/30 text-destructive hover:bg-destructive/10 disabled:opacity-50 transition-colors"
                                  >
                                    <Unplug className="w-4 h-4" />
                                    Disconnect
                                  </button>
                                </>
                              ) : (
                                <button
                                  onClick={() => handleConnect(cat.category, adapter)}
                                  disabled={isSaving}
                                  className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
                                >
                                  {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plug className="w-4 h-4" />}
                                  Connect
                                </button>
                              )}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })
            )}
          </div>
        </section>
      )}

      {/* Always-On Adapters */}
      {alwaysOn.length > 0 && (
        <section className="space-y-4">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            Built-in Sources
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {alwaysOn.map((cat) =>
              cat.adapters.map((adapter) => (
                <div
                  key={`${cat.category}-${adapter.platform}`}
                  className="flex items-center gap-3 px-4 py-3 border rounded-xl bg-card"
                >
                  <span className="text-xl">{adapter.icon}</span>
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-sm">{adapter.name}</div>
                    <div className="text-xs text-muted-foreground capitalize">{cat.category}</div>
                  </div>
                  <span className="flex items-center gap-1 text-xs text-green-500">
                    <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
                    Active
                  </span>
                </div>
              ))
            )}
          </div>
        </section>
      )}

      {/* Footer help text */}
      <div className="text-xs text-muted-foreground text-center pt-4 pb-8 border-t border-border">
        After connecting a service, the dashboard will automatically refresh to display your data.
        API keys are stored locally in your .env configuration file.
      </div>
    </div>
  );
}
