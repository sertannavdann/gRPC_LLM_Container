/**
 * Weather Widget
 *
 * Displays current weather conditions and forecast.
 * Shows temperature, humidity, wind, and upcoming conditions.
 */
'use client';

import React from 'react';
import { WeatherContext, WeatherForecast } from '@/types/dashboard';
import {
  Cloud,
  Sun,
  CloudRain,
  CloudSnow,
  CloudLightning,
  CloudDrizzle,
  Wind,
  Droplets,
  Eye,
  Thermometer,
  Maximize2,
  Minimize2,
} from 'lucide-react';

interface WeatherWidgetProps {
  data: WeatherContext | null;
  expanded?: boolean;
  onFocus?: () => void;
  onCollapse?: () => void;
}

const conditionIcons: Record<string, React.ReactNode> = {
  clear: <Sun className="w-5 h-5 text-yellow-400" />,
  clouds: <Cloud className="w-5 h-5 text-gray-400" />,
  rain: <CloudRain className="w-5 h-5 text-blue-400" />,
  drizzle: <CloudDrizzle className="w-5 h-5 text-blue-300" />,
  thunderstorm: <CloudLightning className="w-5 h-5 text-yellow-500" />,
  snow: <CloudSnow className="w-5 h-5 text-white" />,
  mist: <Cloud className="w-5 h-5 text-gray-300" />,
  fog: <Cloud className="w-5 h-5 text-gray-300" />,
  haze: <Cloud className="w-5 h-5 text-gray-300" />,
};

function getConditionIcon(condition: string, size: 'sm' | 'lg' = 'sm') {
  const icon = conditionIcons[condition?.toLowerCase()] || <Cloud className="w-5 h-5 text-gray-400" />;
  if (size === 'lg') {
    return React.cloneElement(icon as React.ReactElement, { className: 'w-10 h-10' });
  }
  return icon;
}

export function WeatherWidget({ data, expanded, onFocus, onCollapse }: WeatherWidgetProps) {
  if (!data || !data.current) {
    return (
      <div className="bg-gray-800 rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Cloud className="w-4 h-4 text-sky-400" />
            <span className="font-medium text-sm">Weather</span>
          </div>
          {onFocus && (
            <button onClick={onFocus} className="p-1 hover:bg-gray-700 rounded transition-colors">
              <Maximize2 className="w-3.5 h-3.5 text-gray-500" />
            </button>
          )}
        </div>
        <p className="text-sm text-gray-500 text-center py-6">
          No weather data. Connect OpenWeather in Integrations.
        </p>
      </div>
    );
  }

  const { current, forecasts } = data;

  return (
    <div className={`bg-gray-800 rounded-xl p-4 ${expanded ? 'min-h-[400px]' : ''}`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Cloud className="w-4 h-4 text-sky-400" />
          <span className="font-medium text-sm">Weather</span>
          {current.platform !== 'unknown' && (
            <span className="text-xs text-gray-500">{current.platform}</span>
          )}
        </div>
        {expanded && onCollapse ? (
          <button onClick={onCollapse} className="p-1 hover:bg-gray-700 rounded transition-colors">
            <Minimize2 className="w-3.5 h-3.5 text-gray-500" />
          </button>
        ) : onFocus ? (
          <button onClick={onFocus} className="p-1 hover:bg-gray-700 rounded transition-colors">
            <Maximize2 className="w-3.5 h-3.5 text-gray-500" />
          </button>
        ) : null}
      </div>

      {/* Current conditions */}
      <div className="flex items-center gap-4 mb-4">
        <div className="flex-shrink-0">
          {getConditionIcon(current.condition, 'lg')}
        </div>
        <div>
          <div className="text-3xl font-bold">
            {Math.round(current.temperature_celsius)}°C
          </div>
          <div className="text-sm text-gray-400 capitalize">{current.description}</div>
        </div>
        <div className="ml-auto text-right text-xs text-gray-500">
          <div>Feels {Math.round(current.feels_like_celsius)}°C</div>
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="bg-gray-700/50 rounded-lg px-3 py-2 text-center">
          <Droplets className="w-3.5 h-3.5 mx-auto mb-1 text-blue-400" />
          <div className="text-sm font-medium">{current.humidity}%</div>
          <div className="text-xs text-gray-500">Humidity</div>
        </div>
        <div className="bg-gray-700/50 rounded-lg px-3 py-2 text-center">
          <Wind className="w-3.5 h-3.5 mx-auto mb-1 text-gray-400" />
          <div className="text-sm font-medium">{Math.round(current.wind_speed_kmh)} km/h</div>
          <div className="text-xs text-gray-500">Wind</div>
        </div>
        <div className="bg-gray-700/50 rounded-lg px-3 py-2 text-center">
          <Eye className="w-3.5 h-3.5 mx-auto mb-1 text-gray-400" />
          <div className="text-sm font-medium">{Math.round(current.visibility_meters / 1000)} km</div>
          <div className="text-xs text-gray-500">Visibility</div>
        </div>
      </div>

      {/* Forecast */}
      {forecasts.length > 0 && (
        <div>
          <div className="text-xs font-medium text-gray-500 mb-2 uppercase tracking-wider">Forecast</div>
          <div className={`grid gap-2 ${expanded ? 'grid-cols-4' : 'grid-cols-4'}`}>
            {forecasts.slice(0, expanded ? 8 : 4).map((f, i) => (
              <ForecastItem key={f.id || i} forecast={f} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ForecastItem({ forecast }: { forecast: WeatherForecast }) {
  const time = new Date(forecast.forecast_time);
  const hour = time.getHours();
  const label = hour === 0 ? '12am' : hour < 12 ? `${hour}am` : hour === 12 ? '12pm' : `${hour - 12}pm`;

  return (
    <div className="bg-gray-700/30 rounded-lg p-2 text-center">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className="flex justify-center mb-1">
        {getConditionIcon(forecast.condition)}
      </div>
      <div className="text-sm font-medium">{Math.round(forecast.temperature_celsius)}°</div>
      {forecast.precipitation_probability > 0.1 && (
        <div className="text-xs text-blue-400 mt-0.5">
          {Math.round(forecast.precipitation_probability * 100)}%
        </div>
      )}
    </div>
  );
}
