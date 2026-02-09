/**
 * Navigation Widget
 * 
 * Displays commute information and traffic conditions.
 * Shows routes with ETA and traffic levels.
 */
'use client';

import React from 'react';
import { NavigationContext, NavigationRoute } from '@/types/dashboard';
import { 
  Navigation, 
  Car, 
  Clock, 
  MapPin,
  AlertTriangle,
  Maximize2,
  Minimize2,
  Route,
  Gauge
} from 'lucide-react';

interface NavigationWidgetProps {
  data: NavigationContext | null;
  expanded?: boolean;
  onFocus?: () => void;
  onCollapse?: () => void;
}

export function NavigationWidget({ data, expanded, onFocus, onCollapse }: NavigationWidgetProps) {
  if (!data) {
    return (
      <div className="bg-gray-800 rounded-xl p-4 animate-pulse">
        <div className="h-6 bg-gray-700 rounded w-1/3 mb-4"></div>
        <div className="h-32 bg-gray-700 rounded"></div>
      </div>
    );
  }
  
  const formatDuration = (minutes: number) => {
    if (minutes < 60) return `${minutes} min`;
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
  };
  
  const formatDistance = (km: number) => {
    if (km < 1) return `${Math.round(km * 1000)} m`;
    return `${km.toFixed(1)} km`;
  };
  
  const formatETA = (isoString: string) => {
    return new Date(isoString).toLocaleTimeString([], { 
      hour: '2-digit', 
      minute: '2-digit' 
    });
  };
  
  const getTrafficColor = (level: string) => {
    switch (level) {
      case 'light': return 'text-green-400';
      case 'moderate': return 'text-yellow-400';
      case 'heavy': return 'text-red-400';
      default: return 'text-gray-400';
    }
  };
  
  const getTrafficBg = (level: string) => {
    switch (level) {
      case 'light': return 'bg-green-500/10 border-green-500/30';
      case 'moderate': return 'bg-yellow-500/10 border-yellow-500/30';
      case 'heavy': return 'bg-red-500/10 border-red-500/30';
      default: return 'bg-gray-700/50 border-gray-700';
    }
  };
  
  const getTransportIcon = (mode: string) => {
    switch (mode) {
      case 'driving': return <Car className="w-4 h-4" />;
      case 'transit': return <Route className="w-4 h-4" />;
      default: return <Navigation className="w-4 h-4" />;
    }
  };
  
  const RouteCard = ({ route, isPrimary = false }: { route: NavigationRoute; isPrimary?: boolean }) => (
    <div className={`rounded-lg p-4 border ${getTrafficBg(route.traffic_level)} ${
      isPrimary ? 'ring-1 ring-blue-500/30' : ''
    }`}>
      {/* Route Header */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2">
          <div className={`p-2 rounded-lg bg-gray-700 ${getTrafficColor(route.traffic_level)}`}>
            {getTransportIcon(route.transport_mode)}
          </div>
          <div>
            <p className="text-sm font-medium capitalize">{route.transport_mode}</p>
            <p className="text-xs text-gray-500">{route.platform}</p>
          </div>
        </div>
        {isPrimary && (
          <span className="px-2 py-0.5 bg-blue-500/20 text-blue-400 text-xs rounded-full">
            Primary
          </span>
        )}
      </div>
      
      {/* Route Details */}
      <div className="space-y-2">
        {/* Origin */}
        <div className="flex items-start gap-2">
          <div className="w-2 h-2 rounded-full bg-green-400 mt-1.5" />
          <div className="min-w-0 flex-1">
            <p className="text-xs text-gray-400">From</p>
            <p className="text-sm truncate">{route.origin.address}</p>
          </div>
        </div>
        
        {/* Destination */}
        <div className="flex items-start gap-2">
          <div className="w-2 h-2 rounded-full bg-red-400 mt-1.5" />
          <div className="min-w-0 flex-1">
            <p className="text-xs text-gray-400">To</p>
            <p className="text-sm truncate">{route.destination.address}</p>
          </div>
        </div>
      </div>
      
      {/* Stats */}
      <div className="grid grid-cols-3 gap-2 mt-4 pt-3 border-t border-gray-700/50">
        <div>
          <p className="text-xs text-gray-500">Duration</p>
          <p className={`font-semibold ${getTrafficColor(route.traffic_level)}`}>
            {formatDuration(route.duration_minutes)}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Distance</p>
          <p className="font-semibold">{formatDistance(route.distance_km)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">ETA</p>
          <p className="font-semibold">{formatETA(route.estimated_arrival)}</p>
        </div>
      </div>
      
      {/* Traffic Indicator */}
      <div className={`flex items-center gap-2 mt-3 pt-3 border-t border-gray-700/50 ${getTrafficColor(route.traffic_level)}`}>
        {route.traffic_level === 'heavy' ? (
          <AlertTriangle className="w-4 h-4" />
        ) : (
          <Gauge className="w-4 h-4" />
        )}
        <span className="text-sm capitalize">{route.traffic_level} traffic</span>
      </div>
    </div>
  );
  
  const routes = data.routes || [];
  const hasRoutes = routes.length > 0;
  const primaryRoute = data.primary_route || routes[0];
  
  return (
    <div className={`bg-gray-800 rounded-xl p-4 ${expanded ? 'h-full' : ''}`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Navigation className="w-5 h-5 text-blue-400" />
          <h3 className="font-semibold">Navigation</h3>
          {primaryRoute?.traffic_level === 'heavy' && (
            <span className="flex items-center gap-1 px-2 py-0.5 bg-red-500/20 text-red-400 text-xs rounded-full">
              <AlertTriangle className="w-3 h-3" />
              Heavy traffic
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
      
      {/* Content */}
      {!hasRoutes ? (
        <div className="text-center py-6 text-gray-500">
          <Navigation className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p className="text-sm">No routes configured</p>
          <p className="text-xs mt-1">Add your commute in settings</p>
        </div>
      ) : (
        <div className={`space-y-3 ${expanded ? 'overflow-auto max-h-[calc(100vh-200px)]' : ''}`}>
          {/* Primary Route */}
          {primaryRoute && <RouteCard route={primaryRoute} isPrimary />}
          
          {/* Alternative Routes (expanded only) */}
          {expanded && routes.length > 1 && (
            <>
              <h4 className="text-sm text-gray-400 mt-4 mb-2">Alternatives</h4>
              {routes.slice(1).map(route => (
                <RouteCard key={route.id} route={route} />
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}
