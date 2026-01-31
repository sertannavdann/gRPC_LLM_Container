/**
 * Health Widget
 * 
 * Displays health metrics from wearables and health apps.
 * Shows steps, heart rate, HRV, sleep, and readiness scores.
 */
'use client';

import React from 'react';
import { HealthContext } from '@/types/dashboard';
import { 
  Heart, 
  Activity, 
  Moon, 
  Zap,
  Footprints,
  Maximize2,
  Minimize2,
  TrendingUp,
  TrendingDown
} from 'lucide-react';

interface HealthWidgetProps {
  data: HealthContext | null;
  expanded?: boolean;
  onFocus?: () => void;
  onCollapse?: () => void;
}

export function HealthWidget({ data, expanded, onFocus, onCollapse }: HealthWidgetProps) {
  if (!data) {
    return (
      <div className="bg-gray-800 rounded-xl p-4 animate-pulse">
        <div className="h-6 bg-gray-700 rounded w-1/3 mb-4"></div>
        <div className="grid grid-cols-2 gap-3">
          <div className="h-24 bg-gray-700 rounded"></div>
          <div className="h-24 bg-gray-700 rounded"></div>
          <div className="h-24 bg-gray-700 rounded"></div>
          <div className="h-24 bg-gray-700 rounded"></div>
        </div>
      </div>
    );
  }
  
  const getScoreColor = (score: number, thresholds = { low: 50, medium: 70 }) => {
    if (score >= thresholds.medium) return 'text-green-400';
    if (score >= thresholds.low) return 'text-yellow-400';
    return 'text-red-400';
  };
  
  const getProgressColor = (progress: number) => {
    if (progress >= 0.8) return 'bg-green-500';
    if (progress >= 0.5) return 'bg-yellow-500';
    return 'bg-red-500';
  };
  
  const getHRVStatus = (hrv: number) => {
    if (hrv >= 50) return { color: 'text-green-400', status: 'Good', trend: 'up' };
    if (hrv >= 40) return { color: 'text-yellow-400', status: 'Normal', trend: 'flat' };
    return { color: 'text-red-400', status: 'Low', trend: 'down' };
  };
  
  const formatNumber = (num: number) => {
    return new Intl.NumberFormat().format(num);
  };
  
  const stepsProgress = data.steps_progress;
  const hrvStatus = getHRVStatus(data.hrv);
  
  // Metric Card Component
  const MetricCard = ({ 
    icon: Icon, 
    label, 
    value, 
    unit, 
    color, 
    subtext,
    progress
  }: { 
    icon: React.ElementType; 
    label: string; 
    value: string | number; 
    unit?: string;
    color: string;
    subtext?: string;
    progress?: number;
  }) => (
    <div className="bg-gray-700/50 rounded-lg p-3">
      <div className="flex items-center gap-2 mb-2">
        <Icon className={`w-4 h-4 ${color}`} />
        <span className="text-xs text-gray-400">{label}</span>
      </div>
      <div className="flex items-baseline gap-1">
        <span className={`text-xl font-bold ${color}`}>{value}</span>
        {unit && <span className="text-xs text-gray-500">{unit}</span>}
      </div>
      {subtext && (
        <p className="text-xs text-gray-500 mt-1">{subtext}</p>
      )}
      {progress !== undefined && (
        <div className="mt-2">
          <div className="h-1.5 bg-gray-600 rounded-full overflow-hidden">
            <div 
              className={`h-full ${getProgressColor(progress)} transition-all`}
              style={{ width: `${Math.min(progress * 100, 100)}%` }}
            />
          </div>
          <p className="text-xs text-gray-500 mt-1">{Math.round(progress * 100)}% of goal</p>
        </div>
      )}
    </div>
  );
  
  return (
    <div className={`bg-gray-800 rounded-xl p-4 ${expanded ? 'h-full' : ''}`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Heart className="w-5 h-5 text-red-400" />
          <h3 className="font-semibold">Health</h3>
          {data.hrv < 40 && (
            <span className="px-2 py-0.5 bg-red-500/20 text-red-400 text-xs rounded-full">
              Low HRV
            </span>
          )}
        </div>
        
        <div className="flex items-center gap-2">
          {expanded ? (
            <button 
              onClick={onCollapse}
              className="p-1 hover:bg-gray-700 rounded transition-colors"
            >
              <Minimize2 className="w-4 h-4 text-gray-400" />
            </button>
          ) : (
            <button 
              onClick={onFocus}
              className="p-1 hover:bg-gray-700 rounded transition-colors"
            >
              <Maximize2 className="w-4 h-4 text-gray-400" />
            </button>
          )}
        </div>
      </div>
      
      {/* Readiness Score - Hero */}
      <div className={`bg-gradient-to-br from-gray-700/50 to-gray-800 rounded-lg p-4 mb-4 border ${
        data.readiness >= 70 ? 'border-green-500/30' : 
        data.readiness >= 50 ? 'border-yellow-500/30' : 'border-red-500/30'
      }`}>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-gray-400 mb-1">Readiness Score</p>
            <div className="flex items-baseline gap-2">
              <span className={`text-3xl font-bold ${getScoreColor(data.readiness)}`}>
                {data.readiness}
              </span>
              <span className="text-gray-500">/100</span>
            </div>
          </div>
          <div className="relative w-16 h-16">
            <svg className="w-full h-full transform -rotate-90">
              <circle
                cx="32"
                cy="32"
                r="28"
                fill="none"
                stroke="currentColor"
                strokeWidth="4"
                className="text-gray-700"
              />
              <circle
                cx="32"
                cy="32"
                r="28"
                fill="none"
                stroke="currentColor"
                strokeWidth="4"
                strokeDasharray={`${(data.readiness / 100) * 176} 176`}
                className={getScoreColor(data.readiness)}
              />
            </svg>
            <Zap className={`absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-6 h-6 ${getScoreColor(data.readiness)}`} />
          </div>
        </div>
      </div>
      
      {/* Metrics Grid */}
      <div className="grid grid-cols-2 gap-3">
        <MetricCard 
          icon={Footprints}
          label="Steps"
          value={formatNumber(data.steps)}
          color="text-blue-400"
          subtext={`Goal: ${formatNumber(data.steps_goal)}`}
          progress={stepsProgress}
        />
        
        <MetricCard 
          icon={Heart}
          label="Heart Rate"
          value={data.heart_rate}
          unit="bpm"
          color="text-red-400"
          subtext="Current"
        />
        
        <MetricCard 
          icon={Activity}
          label="HRV"
          value={data.hrv}
          unit="ms"
          color={hrvStatus.color}
          subtext={hrvStatus.status}
        />
        
        <MetricCard 
          icon={Moon}
          label="Sleep"
          value={data.sleep_hours.toFixed(1)}
          unit="hrs"
          color={getScoreColor(data.sleep_score)}
          subtext={`Score: ${data.sleep_score}/100`}
        />
      </div>
      
      {/* Expanded View - Additional metrics */}
      {expanded && data.today && (
        <div className="mt-4 pt-4 border-t border-gray-700">
          <h4 className="text-sm text-gray-400 mb-3">Today&apos;s Activity</h4>
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-gray-700/50 rounded-lg p-3">
              <p className="text-xs text-gray-400">Calories Burned</p>
              <p className="text-lg font-semibold text-orange-400">
                {formatNumber(data.today.calories_burned)}
              </p>
            </div>
            <div className="bg-gray-700/50 rounded-lg p-3">
              <p className="text-xs text-gray-400">Active Minutes</p>
              <p className="text-lg font-semibold text-green-400">
                {data.today.active_minutes}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
