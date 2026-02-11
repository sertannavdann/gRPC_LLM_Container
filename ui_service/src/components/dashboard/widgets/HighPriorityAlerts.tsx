/**
 * High Priority Alerts
 * 
 * Displays urgent items that need immediate attention.
 * Based on relevance classification from the dashboard service.
 */
'use client';

import React, { useState } from 'react';
import { RelevanceItem } from '@/types/dashboard';
import { 
  AlertTriangle, 
  Calendar, 
  DollarSign, 
  Heart, 
  Navigation,
  X,
  ChevronRight,
  Bell
} from 'lucide-react';

interface HighPriorityAlertsProps {
  items: RelevanceItem[];
}

export function HighPriorityAlerts({ items }: HighPriorityAlertsProps) {
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set());
  const [isExpanded, setIsExpanded] = useState(true);
  
  const visibleItems = items.filter(item => !dismissedIds.has(`${item.type}-${item.subtype}-${item.title}`));
  
  if (visibleItems.length === 0) return null;
  
  const getIcon = (type: string) => {
    switch (type) {
      case 'calendar': return <Calendar className="w-4 h-4" />;
      case 'finance': return <DollarSign className="w-4 h-4" />;
      case 'health': return <Heart className="w-4 h-4" />;
      case 'navigation': return <Navigation className="w-4 h-4" />;
      default: return <AlertTriangle className="w-4 h-4" />;
    }
  };
  
  const getColor = (type: string) => {
    switch (type) {
      case 'calendar': return 'text-blue-400 bg-blue-500/10 border-blue-500/30';
      case 'finance': return 'text-green-400 bg-green-500/10 border-green-500/30';
      case 'health': return 'text-red-400 bg-red-500/10 border-red-500/30';
      case 'navigation': return 'text-purple-400 bg-purple-500/10 border-purple-500/30';
      default: return 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30';
    }
  };
  
  const handleDismiss = (item: RelevanceItem) => {
    setDismissedIds(prev => new Set([...prev, `${item.type}-${item.subtype}-${item.title}`]));
  };
  
  return (
    <div className="border-b border-yellow-500/30 bg-yellow-500/5">
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center justify-between w-full px-4 py-2 hover:bg-yellow-500/10 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Bell className="w-4 h-4 text-yellow-400" />
          <span className="text-sm font-medium text-yellow-400">
            {visibleItems.length} High Priority Alert{visibleItems.length !== 1 ? 's' : ''}
          </span>
        </div>
        <ChevronRight className={`w-4 h-4 text-yellow-400 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
      </button>
      
      {/* Alerts List */}
      {isExpanded && (
        <div className="px-4 pb-3 space-y-2">
          {visibleItems.map((item, index) => (
            <div 
              key={`${item.type}-${item.subtype}-${index}`}
              className={`flex items-center justify-between gap-3 p-3 rounded-lg border ${getColor(item.type)}`}
            >
              <div className="flex items-center gap-3 min-w-0">
                <div className={`p-1.5 rounded ${getColor(item.type).split(' ').slice(1).join(' ')}`}>
                  {getIcon(item.type)}
                </div>
                <div className="min-w-0">
                  <p className="font-medium text-sm truncate">{item.title}</p>
                  {item.alert && (
                    <p className="text-xs text-gray-400">{item.alert}</p>
                  )}
                </div>
              </div>
              <button
                onClick={() => handleDismiss(item)}
                className="p-1 hover:bg-white/10 rounded transition-colors flex-shrink-0"
                title="Dismiss"
              >
                <X className="w-4 h-4 text-gray-400" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
