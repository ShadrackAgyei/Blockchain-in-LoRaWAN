import { ArrowUp, ArrowDown, Link, Package } from 'lucide-react';
import { cn, getEventTypeColor, formatTimeAgo } from '@/lib/utils';
import type { LiveEvent } from '@/types';

interface EventCardProps {
  event: LiveEvent;
  showDetails?: boolean;
}

function getEventIcon(type: string) {
  switch (type.toLowerCase()) {
    case 'uplink':
      return ArrowUp;
    case 'downlink':
      return ArrowDown;
    case 'join':
      return Link;
    case 'batch_flush':
      return Package;
    default:
      return ArrowUp;
  }
}

export function EventCard({ event, showDetails = true }: EventCardProps) {
  const Icon = getEventIcon(event.type);
  const isBatchEvent = event.type === 'batch_flush';

  return (
    <div className="flex items-start gap-3 rounded-lg bg-white p-4 shadow-sm border border-gray-100">
      {/* Icon */}
      <div
        className={cn(
          'rounded-lg p-2',
          getEventTypeColor(event.type).replace('text-', 'bg-').replace('800', '100')
        )}
      >
        <Icon className={cn('h-5 w-5', getEventTypeColor(event.type).split(' ')[1])} />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span
            className={cn(
              'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
              getEventTypeColor(event.type)
            )}
          >
            {event.type}
          </span>
          <span className="text-xs text-gray-400">
            {formatTimeAgo(event.timestamp)}
          </span>
        </div>

        {isBatchEvent ? (
          <div className="mt-2">
            <p className="text-sm font-medium text-gray-900">
              Gateway: {event.gatewayEui?.slice(0, 12) ?? 'Unknown'}
            </p>
            <div className="mt-1 flex gap-4 text-xs text-gray-500">
              <span>{event.uplinkCount ?? 0} uplinks</span>
              <span>{event.downlinkCount ?? 0} downlinks</span>
              <span>{event.joinCount ?? 0} joins</span>
            </div>
            {event.txId && (
              <p className="mt-1 text-xs text-gray-400 font-mono truncate">
                TX: {event.txId}
              </p>
            )}
          </div>
        ) : (
          <div className="mt-2">
            <p className="text-sm font-medium text-gray-900 truncate">
              Device: {event.devEui ?? 'Unknown'}
            </p>
            {showDetails && event.gatewayEui && (
              <p className="text-xs text-gray-500 truncate">
                via {event.gatewayEui.slice(0, 12)}...
              </p>
            )}
            {showDetails && (event.rssi !== undefined || event.snr !== undefined) && (
              <div className="mt-1 flex gap-3 text-xs">
                {event.rssi !== undefined && (
                  <span className="text-gray-500">
                    RSSI: <span className="font-medium text-gray-700">{event.rssi} dBm</span>
                  </span>
                )}
                {event.snr !== undefined && (
                  <span className="text-gray-500">
                    SNR: <span className="font-medium text-gray-700">{event.snr} dB</span>
                  </span>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Signal Quality Indicator */}
      {!isBatchEvent && event.rssi !== undefined && (
        <SignalQualityIndicator rssi={event.rssi} />
      )}
    </div>
  );
}

function SignalQualityIndicator({ rssi }: { rssi: number }) {
  // RSSI ranges: > -70 = excellent, -70 to -85 = good, -85 to -100 = fair, < -100 = poor
  const bars = rssi > -70 ? 4 : rssi > -85 ? 3 : rssi > -100 ? 2 : 1;

  return (
    <div className="flex items-end gap-0.5 h-5">
      {[1, 2, 3, 4].map((bar) => (
        <div
          key={bar}
          className={cn(
            'w-1 rounded-sm',
            bar <= bars ? 'bg-green-500' : 'bg-gray-200'
          )}
          style={{ height: `${bar * 4 + 4}px` }}
        />
      ))}
    </div>
  );
}
