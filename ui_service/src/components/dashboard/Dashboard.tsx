/**
 * Dashboard Container
 * 
 * Main dashboard component that aggregates all widgets.
 * Uses data-oriented design - widgets receive pre-processed canonical data.
 * Supports fullscreen mode, resizable panels, and flexible layouts.
 */
'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useDashboard } from '@/hooks/useDashboard';
import { CalendarWidget } from './widgets/CalendarWidget';
import { FinanceWidget } from './widgets/FinanceWidget';
import { HealthWidget } from './widgets/HealthWidget';
import { NavigationWidget } from './widgets/NavigationWidget';
import { HighPriorityAlerts } from './widgets/HighPriorityAlerts';
import { AdaptersPanel } from './AdaptersPanel';
import { 
  RefreshCw, 
  Settings, 
  Calendar, 
  DollarSign, 
  Heart, 
  Navigation,
  AlertCircle,
  Loader2,
  Clock,
  Expand,
  Shrink,
  LayoutGrid,
  Rows,
  Columns,
  X,
  PanelLeftClose,
  PanelLeft
} from 'lucide-react';

type ViewMode = 'grid' | 'focus' | 'rows' | 'columns';
type FocusCategory = 'calendar' | 'finance' | 'health' | 'navigation' | null;

interface DashboardProps {
  isFullscreen?: boolean;
  onToggleFullscreen?: () => void;
  onClose?: () => void;
}

export function Dashboard({ isFullscreen = false, onToggleFullscreen, onClose }: DashboardProps) {
  const { 
    context, 
    adapters, 
    finance, 
    calendar, 
    health, 
    navigation,
    isLoading, 
    error, 
    lastUpdated, 
    refresh 
  } = useDashboard({ refreshInterval: 60000 });
  
  const [viewMode, setViewMode] = useState<ViewMode>('grid');
  const [focusCategory, setFocusCategory] = useState<FocusCategory>(null);
  const [showAdapters, setShowAdapters] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [panelSizes, setPanelSizes] = useState({ calendar: 1, finance: 1, health: 1, navigation: 1 });
  const [hiddenPanels, setHiddenPanels] = useState<Set<string>>(new Set());
  
  const handleRefresh = async () => {
    setIsRefreshing(true);
    await refresh();
    setTimeout(() => setIsRefreshing(false), 500);
  };
  
  const handleFocus = (category: FocusCategory) => {
    if (focusCategory === category) {
      setFocusCategory(null);
      setViewMode('grid');
    } else {
      setFocusCategory(category);
      setViewMode('focus');
    }
  };
  
  const togglePanel = (panel: string) => {
    setHiddenPanels(prev => {
      const next = new Set(prev);
      if (next.has(panel)) {
        next.delete(panel);
      } else {
        next.add(panel);
      }
      return next;
    });
  };
  
  // Format last updated time
  const formatLastUpdated = () => {
    if (!lastUpdated) return null;
    const diff = Date.now() - lastUpdated.getTime();
    if (diff < 60000) return 'Just now';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    return lastUpdated.toLocaleTimeString();
  };
  
  // Loading state
  if (isLoading && !context) {
    return (
      <div className={`flex flex-col items-center justify-center text-gray-400 ${isFullscreen ? 'h-screen' : 'h-full min-h-[400px]'}`}>
        <Loader2 className="w-8 h-8 animate-spin mb-4" />
        <p>Loading your dashboard...</p>
      </div>
    );
  }
  
  // Error state
  if (error && !context) {
    return (
      <div className={`flex flex-col items-center justify-center text-red-400 ${isFullscreen ? 'h-screen' : 'h-full min-h-[400px]'}`}>
        <AlertCircle className="w-8 h-8 mb-4" />
        <p className="mb-4">{error}</p>
        <button 
          onClick={handleRefresh}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 transition-colors"
        >
          Try Again
        </button>
      </div>
    );
  }
  
  const getLayoutClass = () => {
    switch (viewMode) {
      case 'rows':
        return 'flex flex-col gap-4';
      case 'columns':
        return 'flex flex-row flex-wrap gap-4';
      case 'grid':
      default:
        return 'grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-4 auto-rows-min';
    }
  };
  
  const visiblePanels = ['calendar', 'finance', 'health', 'navigation'].filter(p => !hiddenPanels.has(p));
  
  return (
    <div className={`flex flex-col bg-gray-900 text-white ${isFullscreen ? 'fixed inset-0 z-50' : 'h-full'}`}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800 flex-shrink-0 bg-gray-900/95 backdrop-blur-sm">
        <div className="flex items-center gap-3">
          {/* Expand/Collapse toggle - most prominent */}
          {onToggleFullscreen && (
            <button
              onClick={onToggleFullscreen}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg transition-all ${
                isFullscreen 
                  ? 'bg-blue-600 text-white hover:bg-blue-500' 
                  : 'bg-gray-800 text-gray-300 hover:bg-gray-700 hover:text-white'
              }`}
              title={isFullscreen ? 'Collapse to Side Panel' : 'Expand to Full View'}
            >
              {isFullscreen ? (
                <><PanelLeft className="w-4 h-4" /><span className="text-sm font-medium">Side Panel</span></>
              ) : (
                <><Expand className="w-4 h-4" /><span className="text-sm font-medium">Expand</span></>
              )}
            </button>
          )}
          <h2 className="text-lg font-semibold">Dashboard</h2>
          {lastUpdated && (
            <span className="flex items-center gap-1 text-xs text-gray-500">
              <Clock className="w-3 h-3" />
              {formatLastUpdated()}
            </span>
          )}
        </div>
        
        <div className="flex items-center gap-2">
          {/* Layout mode toggle */}
          <div className="flex bg-gray-800 rounded-lg p-0.5">
            <button
              onClick={() => { setViewMode('grid'); setFocusCategory(null); }}
              className={`p-1.5 rounded-md transition-colors ${
                viewMode === 'grid' ? 'bg-gray-700 text-white' : 'text-gray-400 hover:text-white'
              }`}
              title="Grid View"
            >
              <LayoutGrid className="w-4 h-4" />
            </button>
            <button
              onClick={() => { setViewMode('rows'); setFocusCategory(null); }}
              className={`p-1.5 rounded-md transition-colors ${
                viewMode === 'rows' ? 'bg-gray-700 text-white' : 'text-gray-400 hover:text-white'
              }`}
              title="Row View"
            >
              <Rows className="w-4 h-4" />
            </button>
            <button
              onClick={() => { setViewMode('columns'); setFocusCategory(null); }}
              className={`p-1.5 rounded-md transition-colors ${
                viewMode === 'columns' ? 'bg-gray-700 text-white' : 'text-gray-400 hover:text-white'
              }`}
              title="Column View"
            >
              <Columns className="w-4 h-4" />
            </button>
          </div>
          
          {/* Panel toggles */}
          <div className="flex bg-gray-800 rounded-lg p-0.5">
            <button
              onClick={() => togglePanel('calendar')}
              className={`p-1.5 rounded-md transition-colors ${
                !hiddenPanels.has('calendar') ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'
              }`}
              title="Toggle Calendar"
            >
              <Calendar className="w-4 h-4" />
            </button>
            <button
              onClick={() => togglePanel('finance')}
              className={`p-1.5 rounded-md transition-colors ${
                !hiddenPanels.has('finance') ? 'bg-green-600 text-white' : 'text-gray-400 hover:text-white'
              }`}
              title="Toggle Finance"
            >
              <DollarSign className="w-4 h-4" />
            </button>
            <button
              onClick={() => togglePanel('health')}
              className={`p-1.5 rounded-md transition-colors ${
                !hiddenPanels.has('health') ? 'bg-red-600 text-white' : 'text-gray-400 hover:text-white'
              }`}
              title="Toggle Health"
            >
              <Heart className="w-4 h-4" />
            </button>
            <button
              onClick={() => togglePanel('navigation')}
              className={`p-1.5 rounded-md transition-colors ${
                !hiddenPanels.has('navigation') ? 'bg-purple-600 text-white' : 'text-gray-400 hover:text-white'
              }`}
              title="Toggle Navigation"
            >
              <Navigation className="w-4 h-4" />
            </button>
          </div>
          
          <button
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
            title="Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
          </button>
          
          <button
            onClick={() => setShowAdapters(true)}
            className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
            title="Manage Adapters"
          >
            <Settings className="w-4 h-4" />
          </button>
          
          {onClose && !isFullscreen && (
            <button
              onClick={onClose}
              className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
              title="Close Dashboard"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
      
      {/* High Priority Alerts */}
      {context?.relevance.high && context.relevance.high.length > 0 && (
        <HighPriorityAlerts items={context.relevance.high} />
      )}
      
      {/* Main Content */}
      <div className="flex-1 overflow-auto p-4">
        {viewMode === 'focus' && focusCategory ? (
          /* Focus View - Single widget expanded */
          <div className="h-full">
            {focusCategory === 'calendar' && (
              <CalendarWidget data={calendar} expanded onCollapse={() => handleFocus(null)} />
            )}
            {focusCategory === 'finance' && (
              <FinanceWidget data={finance} expanded onCollapse={() => handleFocus(null)} />
            )}
            {focusCategory === 'health' && (
              <HealthWidget data={health} expanded onCollapse={() => handleFocus(null)} />
            )}
            {focusCategory === 'navigation' && (
              <NavigationWidget data={navigation} expanded onCollapse={() => handleFocus(null)} />
            )}
          </div>
        ) : (
          /* Grid/Row/Column View */
          <div className={getLayoutClass()}>
            {!hiddenPanels.has('calendar') && (
              <div className={viewMode === 'columns' ? 'flex-1 min-w-[280px]' : ''}>
                <CalendarWidget 
                  data={calendar} 
                  onFocus={() => handleFocus('calendar')} 
                />
              </div>
            )}
            {!hiddenPanels.has('finance') && (
              <div className={viewMode === 'columns' ? 'flex-1 min-w-[280px]' : ''}>
                <FinanceWidget 
                  data={finance} 
                  onFocus={() => handleFocus('finance')} 
                />
              </div>
            )}
            {!hiddenPanels.has('health') && (
              <div className={viewMode === 'columns' ? 'flex-1 min-w-[280px]' : ''}>
                <HealthWidget 
                  data={health} 
                  onFocus={() => handleFocus('health')} 
                />
              </div>
            )}
            {!hiddenPanels.has('navigation') && (
              <div className={viewMode === 'columns' ? 'flex-1 min-w-[280px]' : ''}>
                <NavigationWidget 
                  data={navigation} 
                  onFocus={() => handleFocus('navigation')} 
                />
              </div>
            )}
          </div>
        )}
      </div>
      
      {/* Adapters Panel Modal */}
      {showAdapters && adapters && (
        <AdaptersPanel 
          adapters={adapters} 
          onClose={() => setShowAdapters(false)} 
        />
      )}
    </div>
  );
}
