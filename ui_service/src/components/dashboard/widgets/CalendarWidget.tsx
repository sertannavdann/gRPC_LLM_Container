/**
 * Calendar Widget
 * 
 * Displays upcoming events from the calendar adapter.
 * Shows imminent events with urgency indicators.
 */
'use client';

import React from 'react';
import { CalendarContext, CalendarEvent } from '@/types/dashboard';
import { 
  Calendar, 
  Clock, 
  MapPin, 
  Users, 
  Video, 
  ChevronRight,
  Maximize2,
  Minimize2,
  AlertTriangle
} from 'lucide-react';

interface CalendarWidgetProps {
  data: CalendarContext | null;
  expanded?: boolean;
  onFocus?: () => void;
  onCollapse?: () => void;
}

export function CalendarWidget({ data, expanded, onFocus, onCollapse }: CalendarWidgetProps) {
  if (!data) {
    return (
      <div className="bg-gray-800 rounded-xl p-4 animate-pulse">
        <div className="h-6 bg-gray-700 rounded w-1/3 mb-4"></div>
        <div className="space-y-3">
          <div className="h-16 bg-gray-700 rounded"></div>
          <div className="h-16 bg-gray-700 rounded"></div>
        </div>
      </div>
    );
  }
  
  const formatTime = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };
  
  const formatDate = (isoString: string) => {
    const date = new Date(isoString);
    const today = new Date();
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);
    
    if (date.toDateString() === today.toDateString()) return 'Today';
    if (date.toDateString() === tomorrow.toDateString()) return 'Tomorrow';
    return date.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
  };
  
  const getTimeUntil = (isoString: string) => {
    const diff = new Date(isoString).getTime() - Date.now();
    if (diff < 0) return 'Now';
    if (diff < 3600000) return `in ${Math.round(diff / 60000)}m`;
    if (diff < 86400000) return `in ${Math.round(diff / 3600000)}h`;
    return formatDate(isoString);
  };
  
  const getUrgencyColor = (urgency: string) => {
    switch (urgency) {
      case 'HIGH': return 'border-red-500 bg-red-500/10';
      case 'MEDIUM': return 'border-yellow-500 bg-yellow-500/10';
      default: return 'border-gray-700 bg-gray-800';
    }
  };
  
  const getEventTypeIcon = (eventType: string) => {
    switch (eventType) {
      case 'meeting': return <Video className="w-4 h-4 text-blue-400" />;
      case 'focus_time': return <Clock className="w-4 h-4 text-purple-400" />;
      default: return <Calendar className="w-4 h-4 text-gray-400" />;
    }
  };
  
  const EventCard = ({ event }: { event: CalendarEvent }) => (
    <div className={`border rounded-lg p-3 transition-all hover:bg-gray-700/50 ${getUrgencyColor(event.urgency)}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-start gap-2 min-w-0">
          {getEventTypeIcon(event.event_type)}
          <div className="min-w-0 flex-1">
            <h4 className="font-medium text-sm truncate">{event.title}</h4>
            <div className="flex items-center gap-2 text-xs text-gray-400 mt-1">
              <span>{formatTime(event.start_time)}</span>
              <span>-</span>
              <span>{formatTime(event.end_time)}</span>
            </div>
          </div>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
            event.urgency === 'HIGH' ? 'bg-red-500/20 text-red-400' :
            event.urgency === 'MEDIUM' ? 'bg-yellow-500/20 text-yellow-400' :
            'bg-gray-700 text-gray-400'
          }`}>
            {getTimeUntil(event.start_time)}
          </span>
        </div>
      </div>
      
      {/* Additional details for expanded view */}
      {expanded && (
        <div className="mt-2 pt-2 border-t border-gray-700/50 space-y-1">
          {event.location && (
            <div className="flex items-center gap-1.5 text-xs text-gray-400">
              <MapPin className="w-3 h-3" />
              <span>{event.location.address}</span>
            </div>
          )}
          {event.attendees?.length > 0 && (
            <div className="flex items-center gap-1.5 text-xs text-gray-400">
              <Users className="w-3 h-3" />
              <span>{event.attendees.map(a => a.name).join(', ')}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
  
  const events = data.events || [];
  const next3 = data.next_3 || [];
  const imminent = data.imminent || [];
  const eventsToShow = expanded ? events : next3.length > 0 ? next3 : events.slice(0, 3);
  
  return (
    <div className={`bg-gray-800 rounded-xl p-4 ${expanded ? 'h-full' : ''}`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Calendar className="w-5 h-5 text-blue-400" />
          <h3 className="font-semibold">Calendar</h3>
          {imminent.length > 0 && (
            <span className="flex items-center gap-1 px-2 py-0.5 bg-red-500/20 text-red-400 text-xs rounded-full">
              <AlertTriangle className="w-3 h-3" />
              {imminent.length} imminent
            </span>
          )}
        </div>
        
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">{data.today_count} today</span>
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
      
      {/* Events List */}
      <div className={`space-y-2 ${expanded ? 'overflow-auto max-h-[calc(100vh-200px)]' : ''}`}>
        {eventsToShow.length === 0 ? (
          <div className="text-center py-6 text-gray-500">
            <Calendar className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">No upcoming events</p>
          </div>
        ) : (
          eventsToShow.map(event => (
            <EventCard key={event.id} event={event} />
          ))
        )}
      </div>
      
      {/* Footer - show more link */}
      {!expanded && events.length > 3 && (
        <button
          onClick={onFocus}
          className="flex items-center justify-center gap-1 w-full mt-3 py-2 text-xs text-gray-400 hover:text-white transition-colors"
        >
          <span>View all {events.length} events</span>
          <ChevronRight className="w-3 h-3" />
        </button>
      )}
    </div>
  );
}
