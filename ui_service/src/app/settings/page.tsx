'use client';

import React, { useState, useEffect } from 'react';
import {
  Settings,
  Server,
  Brain,
  Key,
  Eye,
  EyeOff,
  Check,
  AlertCircle,
  Loader2,
  RefreshCw,
  Zap,
  Shield,
  Layers,
  Lock,
  Unlock,
} from 'lucide-react';

interface ProviderInfo {
  models: string[];
  default: string;
}

interface ProviderLockStatus {
  locked: boolean;
  missingRequirements: string[];
  canTest: boolean;
}

interface ConnectionTestResult {
  success: boolean;
  message: string;
  details?: Record<string, unknown>;
}

interface SettingsConfig {
  provider: string;
  model: string;
  hasNimKey: boolean;
  hasPerplexityKey: boolean;
  hasOpenaiKey: boolean;
  hasAnthropicKey: boolean;
  hasSerperKey: boolean;
  delegationEnabled: boolean;
  lidmHeavyModel: string;
  lidmStandardModel: string;
}

type RestartStatus = 'idle' | 'restarting' | 'waiting' | 'ready' | 'error';

const PROVIDER_META: Record<string, { label: string; icon: 'server' | 'brain'; color: string; keyEnvName: string; keyPrefix: string }> = {
  local: { label: 'Local (llama.cpp)', icon: 'server', color: 'text-emerald-400', keyEnvName: '', keyPrefix: '' },
  nvidia: { label: 'NVIDIA NIM (Kimi K2.5)', icon: 'brain', color: 'text-lime-400', keyEnvName: 'NIM_API_KEY', keyPrefix: 'nvapi-' },
  perplexity: { label: 'Perplexity Sonar', icon: 'brain', color: 'text-blue-400', keyEnvName: 'PERPLEXITY_API_KEY', keyPrefix: 'pplx-' },
  openai: { label: 'OpenAI', icon: 'brain', color: 'text-green-400', keyEnvName: 'OPENAI_API_KEY', keyPrefix: 'sk-' },
  anthropic: { label: 'Anthropic Claude', icon: 'brain', color: 'text-orange-400', keyEnvName: 'ANTHROPIC_API_KEY', keyPrefix: 'sk-ant-' },
};

const API_KEY_FIELDS = [
  { key: 'nvidia', label: 'NVIDIA NIM API Key', placeholder: 'nvapi-...' },
  { key: 'perplexity', label: 'Perplexity API Key', placeholder: 'pplx-...' },
  { key: 'openai', label: 'OpenAI API Key', placeholder: 'sk-...' },
  { key: 'anthropic', label: 'Anthropic API Key', placeholder: 'sk-ant-...' },
  { key: 'serper', label: 'Serper API Key (Web Search)', placeholder: '...' },
];

export default function SettingsPage() {
  const [config, setConfig] = useState<SettingsConfig | null>(null);
  const [providers, setProviders] = useState<Record<string, ProviderInfo>>({});
  const [providerLocks, setProviderLocks] = useState<Record<string, ProviderLockStatus>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [restartStatus, setRestartStatus] = useState<RestartStatus>('idle');

  const [selectedProvider, setSelectedProvider] = useState('local');
  const [selectedModel, setSelectedModel] = useState('');
  const [showApiKeys, setShowApiKeys] = useState(false);
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({
    nvidia: '',
    perplexity: '',
    openai: '',
    anthropic: '',
    serper: '',
  });
  const [visibleKeys, setVisibleKeys] = useState<Record<string, boolean>>({});

  // Lock/unlock state
  const [testingProvider, setTestingProvider] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, ConnectionTestResult>>({});

  // LIDM delegation state
  const [delegationEnabled, setDelegationEnabled] = useState(false);
  const [lidmHeavyModel, setLidmHeavyModel] = useState('');
  const [lidmStandardModel, setLidmStandardModel] = useState('');
  const [lidmTierModels, setLidmTierModels] = useState<Record<string, string[]>>({});

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/settings');
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to load settings');
      setConfig(data.config);
      setProviders(data.providers);
      setProviderLocks(data.providerLocks || {});
      setSelectedProvider(data.config.provider);
      setSelectedModel(data.config.model);
      // LIDM
      setDelegationEnabled(data.config.delegationEnabled ?? false);
      setLidmHeavyModel(data.config.lidmHeavyModel || '');
      setLidmStandardModel(data.config.lidmStandardModel || '');
      if (data.lidmTierModels) setLidmTierModels(data.lidmTierModels);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const testProviderConnection = async (providerName: string) => {
    setTestingProvider(providerName);
    setTestResults({ ...testResults, [providerName]: { success: false, message: 'Testing...' } });
    try {
      const res = await fetch('/api/settings/connection-test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: providerName }),
      });
      const result = await res.json();
      setTestResults({ ...testResults, [providerName]: result });

      // If test successful, update lock state
      if (result.success) {
        setProviderLocks({
          ...providerLocks,
          [providerName]: { locked: false, missingRequirements: [], canTest: true },
        });
      }
    } catch (err: any) {
      setTestResults({
        ...testResults,
        [providerName]: { success: false, message: err.message || 'Connection test failed' },
      });
    } finally {
      setTestingProvider(null);
    }
  };

  const reloadOrchestrator = async (): Promise<boolean> => {
    setRestartStatus('restarting');
    try {
      const res = await fetch('/api/settings/reload', { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Reload failed');
      setRestartStatus('ready');
      return true;
    } catch (err: any) {
      setRestartStatus('error');
      setError(err.message);
      return false;
    }
  };

  const saveSettings = async () => {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const hasNewKeys = Object.values(apiKeys).some(v => v.length > 0);
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: selectedProvider,
          model: selectedModel,
          apiKeys: hasNewKeys ? apiKeys : undefined,
          delegation: {
            enabled: delegationEnabled,
            heavyModel: lidmHeavyModel || undefined,
            standardModel: lidmStandardModel || undefined,
          },
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to save');

      setApiKeys({ perplexity: '', openai: '', anthropic: '', serper: '' });
      setShowApiKeys(false);
      setSaving(false);

      const reloaded = await reloadOrchestrator();
      if (reloaded) {
        setSuccess('Settings applied! Config reloaded.');
        await loadSettings();
      }
    } catch (err: any) {
      setError(err.message);
      setSaving(false);
    }
  };

  useEffect(() => {
    if (!providers[selectedProvider]) return;
    const models = providers[selectedProvider].models || [];
    if (!selectedModel || !models.includes(selectedModel)) {
      setSelectedModel(providers[selectedProvider].default);
    }
  }, [selectedProvider, providers, selectedModel]);

  const isBusy = saving || restartStatus === 'restarting' || restartStatus === 'waiting';

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-8">
      {/* Page header */}
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-lg bg-primary/10">
          <Settings className="h-6 w-6 text-primary" />
        </div>
        <div>
          <h1 className="text-xl font-bold">Provider Settings</h1>
          <p className="text-sm text-muted-foreground">
            Configure your LLM provider, model, and API keys
          </p>
        </div>
      </div>

      {/* Provider selection */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">LLM Provider</h2>
        <div className="grid grid-cols-1 gap-3">
          {Object.entries(providers).map(([name, info]) => {
            const meta = PROVIDER_META[name];
            const isSelected = selectedProvider === name;
            const isActive = config?.provider === name;
            const lockStatus = providerLocks[name];
            const isLocked = lockStatus?.locked ?? false;
            const testResult = testResults[name];
            const isTesting = testingProvider === name;

            return (
              <div key={name} className="space-y-2">
                <button
                  onClick={() => !isLocked && setSelectedProvider(name)}
                  disabled={isLocked}
                  className={`relative flex items-center gap-3 p-4 rounded-xl border-2 transition-all w-full ${
                    isSelected
                      ? 'border-primary bg-primary/5 shadow-sm'
                      : isLocked
                      ? 'border-border/50 bg-muted/20 opacity-60 cursor-not-allowed'
                      : 'border-border hover:border-primary/30 hover:bg-muted/30'
                  }`}
                >
                  {isActive && (
                    <span className="absolute top-2 right-2 flex items-center gap-1 text-[10px] text-green-500 font-medium">
                      <Zap className="h-3 w-3" /> Active
                    </span>
                  )}
                  {isLocked && (
                    <span className="absolute top-2 right-2 flex items-center gap-1 text-[10px] text-amber-500 font-medium">
                      <Lock className="h-3 w-3" /> Locked
                    </span>
                  )}
                  <div className={`p-2 rounded-lg ${isSelected ? 'bg-primary/10' : 'bg-muted/50'}`}>
                    {meta?.icon === 'server'
                      ? <Server className={`h-5 w-5 ${meta?.color || ''}`} />
                      : <Brain className={`h-5 w-5 ${meta?.color || ''}`} />
                    }
                  </div>
                  <div className="text-left flex-1">
                    <div className="text-sm font-medium">{meta?.label || name}</div>
                    <div className="text-xs text-muted-foreground">{info.models.length} models</div>
                    {isLocked && lockStatus?.missingRequirements && lockStatus.missingRequirements.length > 0 && (
                      <div className="text-xs text-amber-500 mt-1">
                        Missing: {lockStatus.missingRequirements.join(', ')}
                      </div>
                    )}
                  </div>
                  {isLocked && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        testProviderConnection(name);
                      }}
                      disabled={isTesting}
                      className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
                    >
                      {isTesting ? (
                        <>
                          <Loader2 className="h-3 w-3 animate-spin" />
                          Testing...
                        </>
                      ) : (
                        <>
                          <Unlock className="h-3 w-3" />
                          Unlock
                        </>
                      )}
                    </button>
                  )}
                </button>

                {/* Connection test result */}
                {testResult && (
                  <div className={`flex items-start gap-2 p-3 rounded-lg text-sm ${
                    testResult.success
                      ? 'bg-green-500/10 text-green-600'
                      : 'bg-destructive/10 text-destructive'
                  }`}>
                    {testResult.success ? (
                      <Check className="h-4 w-4 mt-0.5 shrink-0" />
                    ) : (
                      <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                    )}
                    <div className="flex-1">
                      <div className="font-medium">{testResult.message}</div>
                      {testResult.details && Object.keys(testResult.details).length > 0 && (
                        <div className="text-xs mt-1 opacity-80">
                          {JSON.stringify(testResult.details, null, 2)}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* Model selection */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Model</h2>
        <div className="grid gap-2">
          {providers[selectedProvider]?.models.map((model) => (
            <button
              key={model}
              onClick={() => setSelectedModel(model)}
              className={`flex items-center justify-between p-3 rounded-lg border transition-colors ${
                selectedModel === model
                  ? 'border-primary bg-primary/5'
                  : 'border-border hover:border-primary/30'
              }`}
            >
              <span className="text-sm font-mono">{model}</span>
              {selectedModel === model && <Check className="h-4 w-4 text-primary" />}
            </button>
          ))}
        </div>
      </section>

      {/* LIDM Delegation */}
      <section className="space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Multi-Model Delegation (LIDM)</h2>
        <div className="p-4 border rounded-xl space-y-4">
          {/* Enable toggle */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className={`p-2 rounded-lg ${delegationEnabled ? 'bg-violet-500/10' : 'bg-muted/50'}`}>
                <Layers className={`h-5 w-5 ${delegationEnabled ? 'text-violet-400' : 'text-muted-foreground'}`} />
              </div>
              <div>
                <div className="text-sm font-medium">Enable LIDM Delegation</div>
                <div className="text-xs text-muted-foreground">
                  Route queries by complexity to different model tiers
                </div>
              </div>
            </div>
            <button
              onClick={() => setDelegationEnabled(!delegationEnabled)}
              className={`relative w-11 h-6 rounded-full transition-colors ${
                delegationEnabled ? 'bg-violet-500' : 'bg-muted'
              }`}
            >
              <span className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${
                delegationEnabled ? 'translate-x-5' : 'translate-x-0'
              }`} />
            </button>
          </div>

          {delegationEnabled && (
            <div className="space-y-4 pt-2 border-t border-border/50">
              {/* Requirement notice */}
              <div className="flex items-start gap-2 p-3 bg-amber-500/10 rounded-lg">
                <AlertCircle className="h-4 w-4 text-amber-500 mt-0.5 shrink-0" />
                <p className="text-xs text-amber-500">
                  LIDM requires the standard-tier LLM container. Start with:{' '}
                  <code className="font-mono bg-amber-500/10 px-1 rounded">docker compose --profile lidm up -d</code>
                </p>
              </div>

              {/* Heavy tier model */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Heavy Tier Model (complex reasoning)</label>
                <select
                  value={lidmHeavyModel}
                  onChange={(e) => setLidmHeavyModel(e.target.value)}
                  className="w-full p-2 text-sm rounded-lg border bg-background font-mono"
                >
                  {(lidmTierModels.heavy || []).map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </div>

              {/* Standard tier model */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Standard Tier Model (simple queries)</label>
                <select
                  value={lidmStandardModel}
                  onChange={(e) => setLidmStandardModel(e.target.value)}
                  className="w-full p-2 text-sm rounded-lg border bg-background font-mono"
                >
                  {(lidmTierModels.standard || []).map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </div>

              {/* Metrics hint */}
              <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                <Zap className="h-3.5 w-3.5" />
                Monitor delegation metrics in Grafana → gRPC LLM Overview dashboard
              </p>
            </div>
          )}
        </div>
      </section>

      {/* Current config summary */}
      {config && (
        <section className="p-4 bg-muted/30 rounded-xl border space-y-3">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Shield className="h-4 w-4 text-muted-foreground" />
            Current Configuration
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div>
              <span className="text-muted-foreground">Provider: </span>
              <span className="font-mono">{config.provider}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Model: </span>
              <span className="font-mono">{config.model}</span>
            </div>
            <div>
              <span className="text-muted-foreground">LIDM: </span>
              <span className={`font-mono ${config.delegationEnabled ? 'text-violet-400' : ''}`}>
                {config.delegationEnabled ? 'Enabled' : 'Disabled'}
              </span>
            </div>
            {config.delegationEnabled && (
              <div>
                <span className="text-muted-foreground">Tiers: </span>
                <span className="font-mono text-xs">Heavy + Standard</span>
              </div>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {[
              { label: 'NVIDIA', has: config.hasNimKey },
              { label: 'Perplexity', has: config.hasPerplexityKey },
              { label: 'OpenAI', has: config.hasOpenaiKey },
              { label: 'Anthropic', has: config.hasAnthropicKey },
              { label: 'Serper', has: config.hasSerperKey },
            ].map(({ label, has }) => (
              <span key={label} className={`flex items-center gap-1 px-2 py-1 rounded text-xs ${
                has ? 'bg-green-500/10 text-green-500' : 'bg-muted text-muted-foreground'
              }`}>
                {has ? <Check className="h-3 w-3" /> : <AlertCircle className="h-3 w-3" />}
                {label}
              </span>
            ))}
          </div>
        </section>
      )}

      {/* API Keys */}
      <section className="space-y-3">
        <button
          onClick={() => setShowApiKeys(!showApiKeys)}
          className="flex items-center gap-2 text-sm text-primary hover:underline"
        >
          <Key className="h-4 w-4" />
          {showApiKeys ? 'Hide API Keys' : 'Update API Keys'}
        </button>

        {showApiKeys && (
          <div className="space-y-4 p-4 border rounded-xl">
            {API_KEY_FIELDS.map(({ key, label, placeholder }) => (
              <div key={key} className="space-y-1">
                <label className="text-xs font-medium">{label}</label>
                <div className="relative">
                  <input
                    type={visibleKeys[key] ? 'text' : 'password'}
                    value={apiKeys[key]}
                    onChange={(e) => setApiKeys({ ...apiKeys, [key]: e.target.value })}
                    placeholder={placeholder}
                    className="w-full p-2 pr-10 text-sm rounded-lg border bg-background font-mono"
                  />
                  <button
                    onClick={() => setVisibleKeys({ ...visibleKeys, [key]: !visibleKeys[key] })}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted-foreground hover:text-foreground"
                    type="button"
                  >
                    {visibleKeys[key] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>
            ))}
            <p className="text-xs text-muted-foreground">
              Leave empty to keep existing keys. New keys unlock their provider above.
            </p>
          </div>
        )}
      </section>

      {/* Status messages */}
      {restartStatus !== 'idle' && (
        <div className={`flex items-center gap-2 p-3 rounded-lg text-sm ${
          restartStatus === 'error' ? 'bg-destructive/10 text-destructive'
            : restartStatus === 'ready' ? 'bg-green-500/10 text-green-500'
            : 'bg-blue-500/10 text-blue-400'
        }`}>
          {isBusy && <RefreshCw className="h-4 w-4 animate-spin" />}
          {restartStatus === 'ready' && <Check className="h-4 w-4" />}
          {restartStatus === 'error' && <AlertCircle className="h-4 w-4" />}
          {restartStatus === 'restarting' && 'Reloading config...'}
          {restartStatus === 'waiting' && 'Applying changes...'}
          {restartStatus === 'ready' && 'Config reloaded!'}
          {restartStatus === 'error' && (error || 'Restart failed')}
        </div>
      )}

      {error && restartStatus === 'idle' && (
        <div className="flex items-center gap-2 p-3 bg-destructive/10 text-destructive rounded-lg text-sm">
          <AlertCircle className="h-4 w-4" />
          {error}
        </div>
      )}

      {success && restartStatus !== 'error' && (
        <div className="flex items-center gap-2 p-3 bg-green-500/10 text-green-500 rounded-lg text-sm">
          <Check className="h-4 w-4" />
          {success}
        </div>
      )}

      {/* Save button */}
      <div className="flex justify-end pt-2">
        <button
          onClick={saveSettings}
          disabled={isBusy || loading || (providerLocks[selectedProvider]?.locked ?? false)}
          className="flex items-center gap-2 px-6 py-2.5 text-sm font-medium rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          {isBusy && <Loader2 className="h-4 w-4 animate-spin" />}
          {(providerLocks[selectedProvider]?.locked ?? false) ? 'Provider Locked' : isBusy ? 'Applying...' : 'Save & Apply'}
        </button>
      </div>
    </div>
  );
}
