'use client';

import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import type { Gateway } from '@/types';

// Dynamically import Leaflet components to avoid SSR issues
const MapContainer = dynamic(
  () => import('react-leaflet').then((mod) => mod.MapContainer),
  { ssr: false }
);
const TileLayer = dynamic(
  () => import('react-leaflet').then((mod) => mod.TileLayer),
  { ssr: false }
);
const Marker = dynamic(
  () => import('react-leaflet').then((mod) => mod.Marker),
  { ssr: false }
);
const Popup = dynamic(
  () => import('react-leaflet').then((mod) => mod.Popup),
  { ssr: false }
);

interface GatewayMapProps {
  gateways: Gateway[];
  onGatewayClick?: (gateway: Gateway) => void;
  selectedGateway?: string | null;
}

function getTrustColor(score: number): string {
  if (score >= 0.8) return '#22c55e'; // green
  if (score >= 0.5) return '#eab308'; // yellow
  return '#ef4444'; // red
}

export function GatewayMap({
  gateways,
  onGatewayClick,
  selectedGateway,
}: GatewayMapProps) {
  const [isMounted, setIsMounted] = useState(false);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  // Calculate center from gateways or default to Ashesi area
  const center: [number, number] = gateways.length > 0
    ? [
        gateways.reduce((sum, g) => sum + g.location.latitude, 0) / gateways.length,
        gateways.reduce((sum, g) => sum + g.location.longitude, 0) / gateways.length,
      ]
    : [5.759, -0.220]; // Ashesi University area

  if (!isMounted) {
    return (
      <div className="h-full w-full bg-gray-100 rounded-lg flex items-center justify-center">
        <p className="text-gray-500">Loading map...</p>
      </div>
    );
  }

  return (
    <MapContainer
      center={center}
      zoom={12}
      style={{ height: '100%', width: '100%' }}
      className="rounded-lg"
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {gateways.map((gateway) => (
        <GatewayMarker
          key={gateway.gatewayEUI}
          gateway={gateway}
          isSelected={selectedGateway === gateway.gatewayEUI}
          onClick={() => onGatewayClick?.(gateway)}
        />
      ))}
    </MapContainer>
  );
}

interface GatewayMarkerProps {
  gateway: Gateway;
  isSelected: boolean;
  onClick: () => void;
}

function GatewayMarker({ gateway, isSelected, onClick }: GatewayMarkerProps) {
  const [icon, setIcon] = useState<any>(null);

  useEffect(() => {
    // Create custom icon on client side only
    import('leaflet').then((L) => {
      const color = getTrustColor(gateway.trustScore);
      const size = isSelected ? 40 : 30;

      const customIcon = L.divIcon({
        className: 'custom-marker',
        html: `
          <div style="
            width: ${size}px;
            height: ${size}px;
            background-color: ${color};
            border: 3px solid white;
            border-radius: 50%;
            box-shadow: 0 2px 4px rgba(0,0,0,0.3);
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: bold;
            font-size: ${isSelected ? '14px' : '12px'};
          ">
            ${Math.round(gateway.trustScore * 100)}
          </div>
        `,
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
      });

      setIcon(customIcon);
    });
  }, [gateway.trustScore, isSelected]);

  if (!icon) return null;

  return (
    <Marker
      position={[gateway.location.latitude, gateway.location.longitude]}
      icon={icon}
      eventHandlers={{ click: onClick }}
    >
      <Popup>
        <div className="p-2 min-w-[200px]">
          <h3 className="font-bold text-gray-900 mb-2">
            {gateway.gatewayEUI.slice(0, 12)}...
          </h3>
          <div className="space-y-1 text-sm">
            <p>
              <span className="text-gray-500">Owner:</span>{' '}
              <span className="font-medium">{gateway.ownerOrg}</span>
            </p>
            <p>
              <span className="text-gray-500">Trust:</span>{' '}
              <span
                className="font-medium"
                style={{ color: getTrustColor(gateway.trustScore) }}
              >
                {Math.round(gateway.trustScore * 100)}%
              </span>
            </p>
            <p>
              <span className="text-gray-500">Status:</span>{' '}
              <span
                className={`font-medium ${
                  gateway.status === 'ACTIVE' ? 'text-green-600' : 'text-gray-600'
                }`}
              >
                {gateway.status}
              </span>
            </p>
            <p className="text-xs text-gray-400">
              {gateway.location.latitude.toFixed(4)},{' '}
              {gateway.location.longitude.toFixed(4)}
            </p>
          </div>
        </div>
      </Popup>
    </Marker>
  );
}
