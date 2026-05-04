# LoRaWAN Blockchain Dashboard

Custom Next.js dashboard for visualizing the LoRaWAN blockchain network.

## Features

- **Dashboard Home**: Overview stats (gateways, devices, events, charges)
- **Gateway Map**: Interactive Leaflet map with trust score visualization
- **Event Timeline**: Real-time SSE event stream with filtering
- **Billing Dashboard**: Inter-organization charges and settlements

## Development

```bash
# Install dependencies
npm install

# Create environment file
cp .env.local.example .env.local

# Start development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_URL` | Backend API URL | `http://localhost:8000` |

## Production Build

```bash
# Build for production
npm run build

# Start production server
npm start
```

## Docker

The frontend is included in the main `docker-compose.yml`:

```bash
# From project root
docker-compose up -d frontend
```

## Tech Stack

- Next.js 14 (App Router)
- React 18
- TypeScript
- Tailwind CSS
- Leaflet (maps)
- Recharts (charts)
- Lucide React (icons)

## API Endpoints Used

The frontend consumes these backend endpoints:

- `GET /api/gateways` - List gateways with trust scores
- `GET /api/gateways/{eui}` - Gateway details
- `GET /api/gateways/{eui}/history` - Forwarding history
- `GET /api/events/recent` - Historical events
- `GET /api/events/stream` - SSE real-time events
- `GET /api/billing/charges` - Pending charges
- `GET /api/billing/summary` - Billing summary
- `GET /api/stats/overview` - Dashboard stats
