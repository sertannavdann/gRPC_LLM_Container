/**
 * Adapters Panel
 * 
 * Modal panel for managing data source adapters.
 * Allows connecting and disconnecting platforms per category.
 */
'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { AdaptersResponse, Adapter, AdapterCategory } from '@/types/dashboard';
import { useDashboard } from '@/hooks/useDashboard';
import { 
  X, 
  Check, 
  Plus, 
  Loader2, 
  AlertCircle,
  ExternalLink,
  ChevronDown,
  ChevronRight
} from 'lucide-react';

interface AdaptersPanelProps {
  adapters: AdaptersResponse;
  onClose: () => void;
}

export function AdaptersPanel({ adapters, onClose }: AdaptersPanelProps) {
  const router = useRouter();
  const { connectAdapter, disconnectAdapter } = useDashboard();
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(
    new Set(adapters.categories.map(c => c.category))
  );
  const [loadingAdapters, setLoadingAdapters] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  
  const toggleCategory = (category: string) => {
    setExpandedCategories(prev => {
      const next = new Set(prev);
      if (next.has(category)) {
        next.delete(category);
      } else {
        next.add(category);
      }
      return next;
    });
  };
  
  const handleConnect = async (category: string, platform: string) => {
    const key = `${category}-${platform}`;
    setLoadingAdapters(prev => new Set([...prev, key]));
    setError(null);
    
    try {
      const result = await connectAdapter(category, platform);
      if (result?.credentialsRequired) {
        // Redirect to the full Integrations page where credentials can be entered
        onClose();
        router.push(`/integrations?highlight=${platform}`);
        return;
      }
    } catch (err: any) {
      setError(err.message || 'Failed to connect adapter');
    } finally {
      setLoadingAdapters(prev => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    }
  };
  
  const handleDisconnect = async (category: string, platform: string) => {
    const key = `${category}-${platform}`;
    setLoadingAdapters(prev => new Set([...prev, key]));
    setError(null);
    
    try {
      await disconnectAdapter(category, platform);
    } catch (err: any) {
      setError(err.message || 'Failed to disconnect adapter');
    } finally {
      setLoadingAdapters(prev => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    }
  };
  
  const AdapterRow = ({ adapter, category }: { adapter: Adapter; category: string }) => {
    const key = `${category}-${adapter.platform}`;
    const isLoading = loadingAdapters.has(key);
    
    return (
      <div className="flex items-center justify-between py-3 px-3 hover:bg-gray-700/50 rounded-lg transition-colors">
        <div className="flex items-center gap-3">
          <span className="text-xl">{adapter.icon}</span>
          <div>
            <p className="font-medium text-sm">{adapter.name}</p>
            <p className="text-xs text-gray-500">{adapter.platform}</p>
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          {adapter.connected ? (
            <>
              <span className="flex items-center gap-1 text-xs text-green-400">
                <Check className="w-3 h-3" />
                Connected
              </span>
              <button
                onClick={() => handleDisconnect(category, adapter.platform)}
                disabled={isLoading || adapter.platform === 'mock'}
                className="px-3 py-1.5 text-xs bg-red-500/10 text-red-400 hover:bg-red-500/20 rounded-lg transition-colors disabled:opacity-50"
              >
                {isLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Disconnect'}
              </button>
            </>
          ) : (
            <button
              onClick={() => handleConnect(category, adapter.platform)}
              disabled={isLoading}
              className="flex items-center gap-1 px-3 py-1.5 text-xs bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 rounded-lg transition-colors disabled:opacity-50"
            >
              {isLoading ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <>
                  <Plus className="w-3 h-3" />
                  Connect
                </>
              )}
            </button>
          )}
        </div>
      </div>
    );
  };
  
  const CategorySection = ({ category }: { category: AdapterCategory }) => {
    const isExpanded = expandedCategories.has(category.category);
    
    return (
      <div className="border border-gray-700 rounded-lg overflow-hidden">
        <button
          onClick={() => toggleCategory(category.category)}
          className="flex items-center justify-between w-full px-4 py-3 bg-gray-800 hover:bg-gray-700/50 transition-colors"
        >
          <div className="flex items-center gap-3">
            <span className="text-xl">{category.icon}</span>
            <span className="font-medium capitalize">{category.category}</span>
            <span className="text-xs text-gray-500">
              {category.connected_count}/{category.adapters.length} connected
            </span>
          </div>
          {isExpanded ? (
            <ChevronDown className="w-4 h-4 text-gray-400" />
          ) : (
            <ChevronRight className="w-4 h-4 text-gray-400" />
          )}
        </button>
        
        {isExpanded && (
          <div className="p-2 bg-gray-800/50 space-y-1">
            {category.adapters.map(adapter => (
              <AdapterRow 
                key={adapter.platform} 
                adapter={adapter} 
                category={category.category} 
              />
            ))}
          </div>
        )}
      </div>
    );
  };
  
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 rounded-xl max-w-lg w-full max-h-[80vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800">
          <div>
            <h2 className="font-semibold">Data Sources</h2>
            <p className="text-xs text-gray-500">
              {adapters.total_connected} of {adapters.total_available} connected
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-800 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-gray-400" />
          </button>
        </div>
        
        {/* Error */}
        {error && (
          <div className="mx-4 mt-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg flex items-center gap-2 text-red-400">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span className="text-sm">{error}</span>
          </div>
        )}
        
        {/* Categories */}
        <div className="flex-1 overflow-auto p-4 space-y-3">
          {adapters.categories.map(category => (
            <CategorySection key={category.category} category={category} />
          ))}
        </div>
        
        {/* Footer */}
        <div className="px-4 py-3 border-t border-gray-800 bg-gray-800/50 flex items-center justify-between">
          <p className="text-xs text-gray-500">
            Mock adapters are for development. Click Connect to set up real platforms.
          </p>
          <button
            onClick={() => { onClose(); router.push('/integrations'); }}
            className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors"
          >
            <ExternalLink className="w-3 h-3" />
            Manage All
          </button>
        </div>
      </div>
    </div>
  );
}
