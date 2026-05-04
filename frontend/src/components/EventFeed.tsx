'use client';

import { useState, useRef, useEffect } from 'react';
import { Pause, Play, Trash2, Wifi, WifiOff } from 'lucide-react';
import { EventCard } from './EventCard';
import { useEventStream } from '@/lib/useEvents';
import { cn } from '@/lib/utils';
import type { LiveEvent } from '@/types';

interface EventFeedProps {
  eventTypeFilter?: string;
  gatewayFilter?: string;
}

export function EventFeed({ eventTypeFilter, gatewayFilter }: EventFeedProps) {
  const { events, connected, error, clearEvents, reconnect } = useEventStream();
  const [paused, setPaused] = useState(false);
  const [displayEvents, setDisplayEvents] = useState<LiveEvent[]>([]);
  const containerRef = useRef<HTMLDivElement>(null);

  // Update display events when not paused
  useEffect(() => {
    if (!paused) {
      let filtered = events;

      if (eventTypeFilter) {
        filtered = filtered.filter(
          (e) => e.type.toLowerCase() === eventTypeFilter.toLowerCase()
        );
      }

      if (gatewayFilter) {
        filtered = filtered.filter(
          (e) => e.gatewayEui?.toLowerCase().includes(gatewayFilter.toLowerCase())
        );
      }

      setDisplayEvents(filtered);
    }
  }, [events, paused, eventTypeFilter, gatewayFilter]);

  // Auto-scroll to top when new events arrive (if not paused)
  useEffect(() => {
    if (!paused && containerRef.current) {
      containerRef.current.scrollTop = 0;
    }
  }, [displayEvents, paused]);

  return (
    <div className="flex flex-col h-full">
      {/* Status bar */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-50 border-b border-gray-200">
        <div className="flex items-center gap-2">
          {connected ? (
            <>
              <Wifi className="h-4 w-4 text-green-500" />
              <span className="text-sm text-green-600">Connected</span>
            </>
          ) : (
            <>
              <WifiOff className="h-4 w-4 text-red-500" />
              <span className="text-sm text-red-600">
                {error || 'Disconnected'}
              </span>
            </>
          )}
          <span className="text-xs text-gray-400">
            ({displayEvents.length} events)
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setPaused(!paused)}
            className={cn(
              'flex items-center gap-1 rounded px-2 py-1 text-xs font-medium transition-colors',
              paused
                ? 'bg-yellow-100 text-yellow-700 hover:bg-yellow-200'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            )}
          >
            {paused ? (
              <>
                <Play className="h-3 w-3" />
                Resume
              </>
            ) : (
              <>
                <Pause className="h-3 w-3" />
                Pause
              </>
            )}
          </button>
          <button
            onClick={clearEvents}
            className="flex items-center gap-1 rounded bg-gray-100 px-2 py-1 text-xs font-medium text-gray-700 hover:bg-gray-200"
          >
            <Trash2 className="h-3 w-3" />
            Clear
          </button>
          {!connected && (
            <button
              onClick={reconnect}
              className="flex items-center gap-1 rounded bg-primary-100 px-2 py-1 text-xs font-medium text-primary-700 hover:bg-primary-200"
            >
              Reconnect
            </button>
          )}
        </div>
      </div>

      {/* Event list */}
      <div
        ref={containerRef}
        className="flex-1 overflow-y-auto p-4 space-y-3"
        onMouseEnter={() => {
          // Pause on hover
          if (!paused) setPaused(true);
        }}
        onMouseLeave={() => {
          // Resume when mouse leaves (optional behavior)
          // setPaused(false);
        }}
      >
        {displayEvents.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-400">
            <Wifi className="h-12 w-12 mb-4" />
            <p>Waiting for events...</p>
            <p className="text-sm mt-1">
              Events will appear here in real-time
            </p>
          </div>
        ) : (
          displayEvents.map((event, index) => (
            <EventCard key={`${event.timestamp}-${index}`} event={event} />
          ))
        )}
      </div>
    </div>
  );
}
