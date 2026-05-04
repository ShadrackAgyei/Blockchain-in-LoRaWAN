'use client';

import { useEffect, useState } from 'react';
import { Activity, RefreshCw, Filter, X } from 'lucide-react';
import { EventFeed } from '@/components/EventFeed';
import { EventCard } from '@/components/EventCard';
import { getRecentEvents } from '@/lib/api';
import { cn, getEventTypeColor, formatTimestamp } from '@/lib/utils';
import type { Event, LiveEvent } from '@/types';

const EVENT_TYPES = ['uplink', 'join', 'downlink', 'batch_flush'];

export default function EventsPage() {
  const [historicalEvents, setHistoricalEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<'live' | 'history'>('live');
  const [eventTypeFilter, setEventTypeFilter] = useState<string>('');
  const [gatewayFilter, setGatewayFilter] = useState<string>('');
  const [showFilters, setShowFilters] = useState(false);

  const fetchHistoricalEvents = async () => {
    try {
      setLoading(true);
      const data = await getRecentEvents({
        limit: 100,
        eventType: eventTypeFilter || undefined,
        gatewayEui: gatewayFilter || undefined,
      });
      setHistoricalEvents(data);
    } catch (err) {
      console.error('Failed to load events:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (view === 'history') {
      fetchHistoricalEvents();
    }
  }, [view, eventTypeFilter, gatewayFilter]);

  const clearFilters = () => {
    setEventTypeFilter('');
    setGatewayFilter('');
  };

  const hasFilters = eventTypeFilter || gatewayFilter;

  return (
    <div className="h-[calc(100vh-6rem)] flex flex-col space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Events</h1>
          <p className="text-gray-500">
            {view === 'live' ? 'Real-time event stream' : 'Historical events'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* View Toggle */}
          <div className="flex rounded-lg bg-gray-100 p-1">
            <button
              onClick={() => setView('live')}
              className={cn(
                'flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                view === 'live'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-600 hover:text-gray-900'
              )}
            >
              <Activity className="h-4 w-4" />
              Live
            </button>
            <button
              onClick={() => setView('history')}
              className={cn(
                'flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                view === 'history'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-600 hover:text-gray-900'
              )}
            >
              History
            </button>
          </div>

          {/* Filter Toggle */}
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={cn(
              'flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium shadow-sm border transition-colors',
              showFilters || hasFilters
                ? 'bg-primary-50 text-primary-700 border-primary-200'
                : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'
            )}
          >
            <Filter className="h-4 w-4" />
            Filters
            {hasFilters && (
              <span className="ml-1 rounded-full bg-primary-500 px-1.5 text-xs text-white">
                {[eventTypeFilter, gatewayFilter].filter(Boolean).length}
              </span>
            )}
          </button>

          {view === 'history' && (
            <button
              onClick={fetchHistoricalEvents}
              disabled={loading}
              className="flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm border border-gray-200 hover:bg-gray-50 disabled:opacity-50"
            >
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          )}
        </div>
      </div>

      {/* Filters Panel */}
      {showFilters && (
        <div className="rounded-xl bg-white p-4 shadow-sm border border-gray-100">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-900">Filters</h3>
            {hasFilters && (
              <button
                onClick={clearFilters}
                className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700"
              >
                <X className="h-3 w-3" />
                Clear all
              </button>
            )}
          </div>
          <div className="flex flex-wrap gap-4">
            {/* Event Type Filter */}
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">
                Event Type
              </label>
              <div className="flex flex-wrap gap-2">
                {EVENT_TYPES.map((type) => (
                  <button
                    key={type}
                    onClick={() =>
                      setEventTypeFilter(eventTypeFilter === type ? '' : type)
                    }
                    className={cn(
                      'rounded-full px-3 py-1 text-xs font-medium transition-colors',
                      eventTypeFilter === type
                        ? getEventTypeColor(type)
                        : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                    )}
                  >
                    {type}
                  </button>
                ))}
              </div>
            </div>

            {/* Gateway Filter */}
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">
                Gateway EUI
              </label>
              <input
                type="text"
                value={gatewayFilter}
                onChange={(e) => setGatewayFilter(e.target.value)}
                placeholder="Filter by gateway..."
                className="rounded-lg border border-gray-200 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
              />
            </div>
          </div>
        </div>
      )}

      {/* Main Content */}
      <div className="flex-1 min-h-0 rounded-xl bg-white shadow-sm border border-gray-100 overflow-hidden">
        {view === 'live' ? (
          <EventFeed
            eventTypeFilter={eventTypeFilter}
            gatewayFilter={gatewayFilter}
          />
        ) : (
          <div className="h-full overflow-y-auto p-4 space-y-3">
            {loading ? (
              <div className="flex items-center justify-center h-full">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" />
              </div>
            ) : historicalEvents.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-gray-400">
                <Activity className="h-12 w-12 mb-4" />
                <p>No events found</p>
                <p className="text-sm mt-1">
                  Try adjusting your filters
                </p>
              </div>
            ) : (
              historicalEvents.map((event) => (
                <HistoricalEventCard key={event.id} event={event} />
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function HistoricalEventCard({ event }: { event: Event }) {
  // Convert Event to LiveEvent format for EventCard
  const liveEvent: LiveEvent = {
    type: event.eventType,
    devEui: event.devEui,
    gatewayEui: event.gatewayEui,
    rssi: event.rssi,
    snr: event.snr,
    timestamp: event.timestamp,
  };

  return (
    <div className="relative">
      <EventCard event={liveEvent} />
      <div className="absolute top-2 right-2 text-xs text-gray-400">
        #{event.id}
      </div>
    </div>
  );
}
