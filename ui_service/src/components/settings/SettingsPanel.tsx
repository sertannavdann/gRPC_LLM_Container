'use client';

import React, { useState, useEffect } from 'react';
import { Settings, X, Check, AlertCircle, Loader2, Key, Server, Brain, RefreshCw } from 'lucide-react';

interface ProviderInfo {
  models: string[];
  default: string;
}

interface SettingsConfig {
  provider: string;
  model: string;
  hasNimKey: boolean;
  hasPerplexityKey: boolean;
  hasOpenaiKey: boolean;
  hasAnthropicKey: boolean;
  hasSerperKey: boolean;
}

interface SettingsResponse {
  config: SettingsConfig;
  providers: Record<string, ProviderInfo>;
}

type RestartStatus = 'idle' | 'restarting' | 'waiting' | 'ready' | 'error';

export function SettingsPanel({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const [config, setConfig] = useState<SettingsConfig | null>(null);
  const [providers, setProviders] = useState<Record<string, ProviderInfo>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [restartStatus, setRestartStatus] = useState<RestartStatus>('idle');
  
  // Form state
  const [selectedProvider, setSelectedProvider] = useState('local');
  const [selectedModel, setSelectedModel] = useState('');
  const [showApiKeys, setShowApiKeys] = useState(false);
  const [apiKeys, setApiKeys] = useState({
    nvidia: '',
    perplexity: '',
    openai: '',
    anthropic: '',
    serper: '',
  });

  // Load settings on open
  useEffect(() => {
    if (isOpen) {
      loadSettings();
      setRestartStatus('idle');
    }
  }, [isOpen]);

  const loadSettings = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await fetch('/api/settings');
      const data: SettingsResponse = await response.json();
      
      if (!response.ok) {
        throw new Error((data as any).error || 'Failed to load settings');
      }
      
      setConfig(data.config);
      setProviders(data.providers);
      setSelectedProvider(data.config.provider);
      setSelectedModel(data.config.model);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const waitForOrchestrator = async (maxAttempts = 30): Promise<boolean> => {
    for (let i = 0; i < maxAttempts; i++) {
      try {
        // Try a simple chat request to verify orchestrator is responding
        const response = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: 'ping', threadId: 'health-check' }),
        });
        
        if (response.ok) {
          return true;
        }
      } catch {
        // Ignore errors, keep waiting
      }
      
      // Wait 1 second between attempts
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
    return false;
  };

  const restartOrchestrator = async () => {
    setRestartStatus('restarting');
    
    try {
      const response = await fetch('/api/orchestrator', {
        method: 'POST',
      });
      
      const data = await response.json();
      
      if (data.manualRequired) {
        setRestartStatus('error');
        setError('Auto-restart not available. Please run: docker compose restart orchestrator');
        return false;
      }
      
      if (!response.ok) {
        throw new Error(data.error || 'Failed to restart orchestrator');
      }
      
      // Wait for orchestrator to come back up
      setRestartStatus('waiting');
      
      // Give it a moment to start shutting down
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      const isReady = await waitForOrchestrator();
      
      if (isReady) {
        setRestartStatus('ready');
        return true;
      } else {
        setRestartStatus('error');
        setError('Orchestrator did not respond after restart. Please check logs.');
        return false;
      }
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
      const response = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: selectedProvider,
          model: selectedModel,
          apiKeys: showApiKeys ? apiKeys : undefined,
        }),
      });
      
      const data = await response.json();
      
      if (!response.ok) {
        throw new Error(data.error || 'Failed to save settings');
      }
      
      // Clear API key inputs after save
      setApiKeys({ nvidia: '', perplexity: '', openai: '', anthropic: '', serper: '' });
      setShowApiKeys(false);
      
      // Auto-restart orchestrator
      setSaving(false);
      const restarted = await restartOrchestrator();
      
      if (restarted) {
        setSuccess('Settings applied! Orchestrator restarted successfully.');
        // Reload settings to confirm
        await loadSettings();
      }
    } catch (err: any) {
      setError(err.message);
      setSaving(false);
    }
  };

  // Update model when provider changes
  useEffect(() => {
    if (!providers[selectedProvider]) return;
    const models = providers[selectedProvider].models || [];
    if (!selectedModel || !models.includes(selectedModel)) {
      setSelectedModel(providers[selectedProvider].default);
    }
  }, [selectedProvider, providers, selectedModel]);

  if (!isOpen) return null;

  const providerIcons: Record<string, React.ReactNode> = {
    local: <Server className="h-4 w-4" />,
    nvidia: <Brain className="h-4 w-4" />,
    perplexity: <Brain className="h-4 w-4" />,
    openai: <Brain className="h-4 w-4" />,
    anthropic: <Brain className="h-4 w-4" />,
  };

  const providerLabels: Record<string, string> = {
    local: 'Local (llama.cpp)',
    nvidia: 'NVIDIA NIM (Kimi K2.5)',
    perplexity: 'Perplexity Sonar',
    openai: 'OpenAI',
    anthropic: 'Anthropic Claude',
  };

  const restartStatusMessages: Record<RestartStatus, string> = {
    idle: '',
    restarting: 'Restarting orchestrator...',
    waiting: 'Waiting for orchestrator to be ready...',
    ready: 'Orchestrator is ready!',
    error: 'Restart failed',
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-card border rounded-lg shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b">
          <div className="flex items-center gap-2">
            <Settings className="h-5 w-5" />
            <h2 className="text-lg font-semibold">Provider Settings</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 hover:bg-muted rounded"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-4 space-y-6">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <>
              {/* Provider Selection */}
              <div className="space-y-2">
                <label className="text-sm font-medium">LLM Provider</label>
                <div className="grid grid-cols-2 gap-2">
                  {Object.keys(providers).map((provider) => (
                    <button
                      key={provider}
                      onClick={() => setSelectedProvider(provider)}
                      className={`flex items-center gap-2 p-3 rounded-lg border transition-colors ${
                        selectedProvider === provider
                          ? 'border-primary bg-primary/10'
                          : 'border-border hover:border-primary/50'
                      }`}
                    >
                      {providerIcons[provider]}
                      <span className="text-sm">{providerLabels[provider] || provider}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Model Selection */}
              <div className="space-y-2">
                <label className="text-sm font-medium">Model</label>
                <select
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  className="w-full p-2 rounded-lg border bg-background"
                >
                  {providers[selectedProvider]?.models.map((model) => (
                    <option key={model} value={model}>
                      {model}
                    </option>
                  ))}
                </select>
              </div>

              {/* Current Status */}
              {config && (
                <div className="p-3 bg-muted/50 rounded-lg space-y-2">
                  <div className="text-sm font-medium">Current Configuration</div>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="flex items-center gap-1">
                      <span className="text-muted-foreground">Provider:</span>
                      <span className="font-mono">{config.provider}</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <span className="text-muted-foreground">Model:</span>
                      <span className="font-mono">{config.model}</span>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2 mt-2">
                    <KeyIndicator label="NVIDIA" hasKey={config.hasNimKey} />
                    <KeyIndicator label="Perplexity" hasKey={config.hasPerplexityKey} />
                    <KeyIndicator label="OpenAI" hasKey={config.hasOpenaiKey} />
                    <KeyIndicator label="Anthropic" hasKey={config.hasAnthropicKey} />
                    <KeyIndicator label="Serper" hasKey={config.hasSerperKey} />
                  </div>
                </div>
              )}

              {/* API Keys Section */}
              <div className="space-y-2">
                <button
                  onClick={() => setShowApiKeys(!showApiKeys)}
                  className="flex items-center gap-2 text-sm text-primary hover:underline"
                >
                  <Key className="h-4 w-4" />
                  {showApiKeys ? 'Hide API Keys' : 'Update API Keys'}
                </button>
                
                {showApiKeys && (
                  <div className="space-y-3 p-3 border rounded-lg">
                    <ApiKeyInput
                      label="NVIDIA NIM API Key"
                      value={apiKeys.nvidia}
                      onChange={(v) => setApiKeys({ ...apiKeys, nvidia: v })}
                      placeholder="nvapi-..."
                    />
                    <ApiKeyInput
                      label="Perplexity API Key"
                      value={apiKeys.perplexity}
                      onChange={(v) => setApiKeys({ ...apiKeys, perplexity: v })}
                      placeholder="pplx-..."
                    />
                    <ApiKeyInput
                      label="OpenAI API Key"
                      value={apiKeys.openai}
                      onChange={(v) => setApiKeys({ ...apiKeys, openai: v })}
                      placeholder="sk-..."
                    />
                    <ApiKeyInput
                      label="Anthropic API Key"
                      value={apiKeys.anthropic}
                      onChange={(v) => setApiKeys({ ...apiKeys, anthropic: v })}
                      placeholder="sk-ant-..."
                    />
                    <ApiKeyInput
                      label="Serper API Key (Web Search)"
                      value={apiKeys.serper}
                      onChange={(v) => setApiKeys({ ...apiKeys, serper: v })}
                      placeholder="..."
                    />
                    <p className="text-xs text-muted-foreground">
                      Leave empty to keep existing keys. Keys are stored in the .env file.
                    </p>
                  </div>
                )}
              </div>

              {/* Restart Status */}
              {restartStatus !== 'idle' && (
                <div className={`flex items-center gap-2 p-3 rounded-lg ${
                  restartStatus === 'error' 
                    ? 'bg-destructive/10 text-destructive'
                    : restartStatus === 'ready'
                    ? 'bg-green-500/10 text-green-600'
                    : 'bg-blue-500/10 text-blue-600'
                }`}>
                  {(restartStatus === 'restarting' || restartStatus === 'waiting') && (
                    <RefreshCw className="h-4 w-4 animate-spin" />
                  )}
                  {restartStatus === 'ready' && <Check className="h-4 w-4" />}
                  {restartStatus === 'error' && <AlertCircle className="h-4 w-4" />}
                  <span className="text-sm">{restartStatusMessages[restartStatus]}</span>
                </div>
              )}

              {/* Messages */}
              {error && restartStatus === 'idle' && (
                <div className="flex items-center gap-2 p-3 bg-destructive/10 text-destructive rounded-lg">
                  <AlertCircle className="h-4 w-4" />
                  <span className="text-sm">{error}</span>
                </div>
              )}
              
              {success && restartStatus === 'idle' && (
                <div className="flex items-center gap-2 p-3 bg-green-500/10 text-green-600 rounded-lg">
                  <Check className="h-4 w-4" />
                  <span className="text-sm">{success}</span>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 p-4 border-t">
          <button
            onClick={onClose}
            disabled={restartStatus === 'restarting' || restartStatus === 'waiting'}
            className="px-4 py-2 text-sm rounded-lg border hover:bg-muted disabled:opacity-50"
          >
            {restartStatus === 'ready' ? 'Close' : 'Cancel'}
          </button>
          <button
            onClick={saveSettings}
            disabled={saving || loading || restartStatus === 'restarting' || restartStatus === 'waiting'}
            className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {(saving || restartStatus === 'restarting' || restartStatus === 'waiting') && (
              <Loader2 className="h-4 w-4 animate-spin" />
            )}
            {restartStatus === 'restarting' || restartStatus === 'waiting' 
              ? 'Applying...' 
              : 'Save & Apply'}
          </button>
        </div>
      </div>
    </div>
  );
}

function KeyIndicator({ label, hasKey }: { label: string; hasKey: boolean }) {
  return (
    <div className={`flex items-center gap-1 px-2 py-1 rounded text-xs ${
      hasKey ? 'bg-green-500/10 text-green-600' : 'bg-muted text-muted-foreground'
    }`}>
      {hasKey ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}
      {label}
    </div>
  );
}

function ApiKeyInput({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium">{label}</label>
      <input
        type="password"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full p-2 text-sm rounded border bg-background font-mono"
      />
    </div>
  );
}
