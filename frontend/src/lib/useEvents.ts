'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import type { LiveEvent } from '@/types';
import { getEventStreamUrl } from './api';

const MAX_EVENTS = 100;

export function useEventStream() {
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  const connect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const eventSource = new EventSource(getEventStreamUrl());
    eventSourceRef.current = eventSource;

    eventSource.onopen = () => {
      setConnected(true);
      setError(null);
    };

    eventSource.onmessage = (e) => {
      try {
        const event: LiveEvent = JSON.parse(e.data);

        // Skip keepalive messages
        if (event.type === 'keepalive' || event.type === 'connected') {
          return;
        }

        setEvents((prev) => {
          const newEvents = [event, ...prev];
          // Keep only the most recent events
          return newEvents.slice(0, MAX_EVENTS);
        });
      } catch (err) {
        console.error('Failed to parse event:', err);
      }
    };

    eventSource.onerror = () => {
      setConnected(false);
      setError('Connection lost. Reconnecting...');

      // Reconnect after delay
      setTimeout(() => {
        if (eventSourceRef.current === eventSource) {
          connect();
        }
      }, 3000);
    };
  }, []);

  const disconnect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setConnected(false);
  }, []);

  const clearEvents = useCallback(() => {
    setEvents([]);
  }, []);

  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  return {
    events,
    connected,
    error,
    clearEvents,
    reconnect: connect,
  };
}
