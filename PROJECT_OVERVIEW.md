# LoRaWAN Blockchain Project — Complete Overview

> **Capstone Project**: Using Blockchain to Build Decentralised LoRaWAN Networks  
> **Institution**: Ashesi University, B.Sc. Computer Engineering  
> **Reference paper**: Lin et al., *"Using blockchain to build trusted LoRaWAN sharing server"*, IJCS 2017

---

## What the project does (in one paragraph)

LoRaWAN is a low-power wireless network used by IoT devices. Gateways pick up signals from devices and forward them to a network server. In shared deployments, one organisation's device might be picked up by another organisation's gateway — this is called **roaming**. The problem is: how do you know whether to trust a gateway you don't own, and how do you fairly charge for roaming traffic without a central authority? This project answers both questions by recording all gateway activity and billing events on a **Hyperledger Fabric blockchain**, creating an immutable, auditable ledger that no single party controls.

---

## System architecture

```
┌──────────────┐      LoRa RF      ┌─────────────────────┐
│  End Devices │ ─────────────────▶│      Gateways        │
│  (ESP32+LoRa)│                   │  (RPi 5 + RAK5146)   │
│  OTAA auth   │                   │  Basics Station fw   │
└──────────────┘                   └──────────┬──────────┘
                                              │ Basics Station protocol
                                              ▼
                                   ┌─────────────────────┐
                                   │   TTN Network Server │
                                   │   (Docker, self-host)│
                                   └──────────┬──────────┘
                                              │ HTTP Webhooks
                          ┌───────────────────▼───────────────────┐
                          │         Webhook Listener               │
                          │         (Python FastAPI)               │
                          │                                        │
                          │  ┌─────────────┐  ┌───────────────┐  │
                          │  │ Aggregator  │  │  OrgResolver  │  │
                          │  │ (buffers    │  │  (EUI → org   │  │
                          │  │  per-gw)   │  │   mapping)    │  │
                          │  └──────┬──────┘  └───────────────┘  │
                          └─────────┼─────────────────────────────┘
                    ┌──────────────┬┴──────────────┐
                    │              │               │
                    ▼              ▼               ▼
           ┌──────────────┐  ┌─────────┐  ┌──────────────┐
           │  Hyperledger │  │  MySQL  │  │  Prometheus  │
           │  Fabric      │  │  (audit │  │  + Dashboard │
           │  blockchain  │  │  trail) │  │  (metrics)   │
           │              │  └─────────┘  └──────────────┘
           │ TrustMgmt +  │
           │ Billing      │
           └──────────────┘
```

---

## Components

### 1. End Devices

**Hardware**: ESP32 microcontroller + LoRa radio module.

Devices communicate using the **LoRaWAN protocol** — a low-power, long-range radio protocol suited for IoT sensors. They authenticate using **OTAA (Over-the-Air Activation)**, which means on first contact they perform a key exchange with the network server to get session keys. After that, every packet they send is encrypted and authenticated.

Devices don't know or care which gateway picks them up. They just broadcast into the air.

---

### 2. Gateways

**Hardware**: Raspberry Pi 5 + RAK5146 LoRa concentrator board + antenna.

A gateway is a radio receiver — its job is to listen for LoRa transmissions from nearby devices and forward the raw packets to the network server over the internet. It does not decrypt the data; it just relays it.

Gateways run **Basics Station** firmware, which handles the radio configuration and the secure connection to the TTN network server.

In a shared network, **any organisation can own a gateway**, and any device in range will use it. The gateway owner gets credited for providing forwarding capacity. This is what creates the trust and billing problem.

---

### 3. TTN (The Things Network) Stack

**Software**: Self-hosted TTN community stack in Docker.

TTN is the LoRaWAN network server. Its responsibilities:

- Receives raw packets from gateways via the Basics Station protocol
- Performs device authentication (verifies join requests, validates OTAA)
- Decrypts application payloads using session keys
- De-duplicates packets (multiple gateways may hear the same transmission)
- Delivers the decoded message to the application via **webhooks**

TTN sits in the middle of the radio network. It knows which gateways heard each packet, including the RSSI (signal strength) and SNR (signal-to-noise ratio) that each gateway reported.

---

### 4. Webhook Listener

**Software**: Python FastAPI application, port 8000.

This is the bridge between TTN and the blockchain. TTN is configured to POST an HTTP request to this service every time a packet is received. The listener has four distinct responsibilities:

#### 4a. Receiving webhooks

The `/webhook/uplink`, `/webhook/join`, and `/webhook/downlink` endpoints receive TTN's JSON payloads. Each payload contains:

- Device EUI (unique device identifier)
- Gateway EUI (which gateway forwarded it)
- RSSI and SNR (signal quality measured by that gateway)
- Timestamp and frame counter

The signature is verified via HMAC-SHA256 using a shared secret configured in TTN, so only genuine TTN traffic is accepted.

#### 4b. OrgResolver

A lookup table mapping device EUIs and gateway EUIs to their owning organisation (Org1 or Org2). This is needed to determine two things:

- **For trust**: which org to credit when submitting a forwarding record
- **For billing**: whether a packet is a roaming event (device org ≠ gateway org)

In the current implementation this mapping is configured in memory at startup. In a production system it would be backed by a registry query.

#### 4c. Aggregator

Writing every individual packet to the blockchain would be expensive and slow — a single busy gateway might forward thousands of packets per hour. Instead, the aggregator **buffers events per gateway** and writes to the blockchain in batches.

Each `GatewayBuffer` tracks:
- Counts: uplinks, downlinks, joins, errors
- Running sum of RSSI and SNR readings (for computing averages)
- The period start timestamp

Flushing is triggered either by a configurable time window (default: 300 seconds) or manually via the `/admin/flush` endpoint. When flushed, the buffer's aggregate statistics become a single blockchain transaction.

#### 4d. Fabric Client

The component that actually talks to Hyperledger Fabric. It does this by **shelling out to the `peer` CLI binary** — constructing the correct environment variables (MSP identity, TLS certificates, peer addresses) and running `peer chaincode invoke` or `peer chaincode query` as subprocesses.

Each invoke is sent to both peers (Org1 and Org2) to satisfy the endorsement policy, then submitted to the orderer for ordering and commitment.

---

### 5. Hyperledger Fabric Blockchain

**Software**: Hyperledger Fabric test network, 2 organisations, `lorawan-channel`, Raft consensus.

Fabric is a **permissioned blockchain** — only known, credentialed participants can submit transactions. There is no cryptocurrency. The two organisations (Org1, Org2) each run a peer node, and a single orderer sequences transactions into blocks.

Every transaction is signed with the submitter's X.509 certificate, so the chaincode can check `GetMSPID()` to know which org is making the call. This is the foundation of the access control in both chaincodes.

The blockchain holds two chaincodes (smart contracts):

---

### 6. TrustManagement Chaincode

**Language**: Go. **Location**: `chaincode/trustmanagement/`

This chaincode manages the reputation of gateways over time.

#### Gateway registration

When an operator deploys a gateway they call `RegisterGateway`, passing the gateway EUI, their org name, and the physical coordinates. The chaincode checks that `clientMSPID == ownerOrg + "MSP"` — so Org2 cannot register a gateway and claim it belongs to Org1.

The gateway record is stored on the ledger under the key `GATEWAY_<EUI>` with an initial trust score of **0.5** (neutral). An org-indexed composite key `org~gateway` is also written for efficient org-scoped queries.

#### Forwarding records

When the webhook listener flushes a batch, it calls `RecordForwardingBatch` with the aggregated stats for that period. Each record is stored under `RECORD_FR_<EUI>_<timestamp>` and indexed by `gateway~time` composite key so records can be retrieved in time order.

#### Trust score computation

`ComputeTrustScore` is called after each batch is recorded. It:

1. Fetches all forwarding records from the past 90 days
2. For each record, calculates two components:
   - **Reliability** = 1 − (error_count / total_packets) — higher is better
   - **Signal quality** = average of normalised RSSI (−120 to −40 dBm → 0–1) and normalised SNR (−20 to +10 dB → 0–1)
3. Applies **exponential decay** to each record's contribution based on its age, with a 30-day half-life — so last week's behaviour counts far more than last month's
4. Combines the two components: **60% reliability + 40% signal quality**
5. Applies a 5% inactivity penalty if the gateway has not submitted a record in the past 7 days
6. Clamps the result to [0, 1]

The computed score is written back to the `Gateway` record on the ledger.

#### Threshold-based routing

`GetTrustedGateways(minTrustScore)` returns all ACTIVE gateways with a score at or above the threshold, sorted descending. The operational threshold is **0.70** — below this, a gateway is considered unreliable and excluded from roaming acceptance decisions.

---

### 7. Billing Chaincode

**Language**: Go. **Location**: `chaincode/billing/`

This chaincode tracks the money owed between organisations for roaming traffic.

#### Policies

A **home network** (the org that owns the devices) creates a `Policy` on the ledger. The policy declares:

- Which device EUIs are covered
- Which packet types are billable (UPLINK, DOWNLINK, JOIN)
- The price per packet type in **microcents** (1 microcent = 0.00001 cents)
  - Default: uplink = 100, downlink = 200, join = 500
- A validity window (valid_from, valid_until)

The chaincode derives the policy owner from `getCallerOrg()` — the MSP identity of whoever submitted the transaction — so a policy's `ownerOrg` is always the org that actually called it. This prevents one org from creating a policy pretending to be another.

#### Recording charges

When a roaming event arrives (device org ≠ gateway org), the webhook listener calls `RecordCharge`. The chaincode:

1. Finds the active policy for the device by looking up the `device~policy` composite key index
2. Confirms the device org and gateway org differ (same-org traffic is not charged)
3. Looks up the price for the packet type from the policy
4. Appends the charge to a **`ChargeAccumulator`** keyed by the pair `(debtorOrg, creditorOrg)`

The accumulator is an on-ledger running total. Charges accumulate there continuously.

#### Settlement flow

Settlement is a three-step process:

1. **Initiate** — either org calls `InitiateSettlement`. The current accumulator total is frozen into a `Settlement` record (status: PENDING), and the accumulator is reset to zero for the next period.
2. **Confirm** — the creditor org calls `ConfirmPayment` with an off-chain payment reference (bank transfer ID, etc). Status becomes PAID.
3. **Dispute** — either org can call `DisputeSettlement` with a reason if they disagree with the total.

Actual money moves off-chain. The blockchain is the **authoritative record** of what was agreed, confirmed, or disputed — not a payment processor.

---

### 8. MySQL Database

**Port**: 3307. **Container**: `lorawan-mysql`.

MySQL serves as a local event cache and audit trail. Every time the aggregator flushes a batch to the blockchain, the same data is also written to MySQL. This provides:

- Fast queryable history without hitting the blockchain for every dashboard request
- A backup record if the blockchain node is temporarily unreachable
- The data source for the dashboard's time-series graphs

MySQL does not replace the blockchain — the blockchain is the authoritative record. MySQL is the read-optimised copy for the application layer.

---

### 9. Dashboard and Monitoring

**Dashboard**: Next.js frontend, port 3000. Reads from the webhook listener's API (`/stats`, SSE events for live updates).

**Prometheus**: port 9090. Scrapes metrics from the webhook listener's `/metrics` endpoint, which exposes counters for webhook requests, blockchain transaction latency, aggregator flushes, and error rates.

**Grafana** (optional, port 3001): Reads from Prometheus for time-series visualisation. The custom Next.js dashboard is the primary UI.

---

## How everything connects — the data flow

### Normal uplink (same-org device and gateway)

```
Device sends LoRa packet
  → Gateway picks it up, forwards to TTN
    → TTN decodes, POSTs to /webhook/uplink
      → Listener parses payload, extracts gateway EUI + signal metrics
        → OrgResolver: device org == gateway org (not roaming)
          → EventAggregator buffers the event
            → [after window or flush] Aggregator calls FabricClient
              → FabricClient runs: peer chaincode invoke ... RecordForwardingBatch
                → Fabric records it on lorawan-channel
                  → MySQL also stores the batch
                    → Dashboard updates via SSE
```

### Roaming uplink (device and gateway belong to different orgs)

Same flow as above, but the OrgResolver detects the org mismatch. After recording the forwarding batch, the listener also calls:

```
FabricClient → peer chaincode invoke ... RecordCharge
  → Billing chaincode finds the device's active policy
    → Calculates charge = packet_count × price_per_type
      → Adds to ChargeAccumulator[debtorOrg → creditorOrg]
```

### Trust score update (after each simulation round)

```
FabricClient → peer chaincode invoke ... ComputeTrustScore(gatewayEUI)
  → TrustManagement fetches records from past 90 days
    → Applies decay-weighted reliability + signal formula
      → Writes new score back to Gateway record on ledger
        → Caller reads score via GetGateway query
```

### Settlement

```
Org2 admin → peer chaincode invoke ... InitiateSettlement(Org2, Org1)
  → Chaincode freezes accumulator into Settlement record (PENDING)
    → Org2 pays Org1 off-chain (bank transfer)
      → Org1 admin → peer chaincode invoke ... ConfirmPayment(settlementID, paymentRef)
        → Settlement status → PAID, payment reference recorded on-chain
```

---

## Simulation

The evaluation simulation (`scripts/simulate.py`) replaces real hardware with synthetic data to demonstrate the system at scale.

**8 gateways** are created with distinct statistical profiles:

| Profile | Count | Error rate | RSSI range | SNR range |
|---|---|---|---|---|
| Reliable | 3 | 1–2% | −68 to −75 dBm | 7.5–9.0 dB |
| Average | 2 | 7–8% | −88 to −90 dBm | 3.5–4.0 dB |
| Poor | 2 | 18–20% | −102 to −105 dBm | −0.5 to 0.5 dB |
| Degrading | 1 | 2% → 30% | −70 → −105 dBm | 8.0 → 0.0 dB |

**Per round** (10 rounds total, 800 events total):

1. `generate_events_for_round` creates 10 events per gateway (80 total). For each event:
   - A random device is selected from the 6 simulated devices (4 Org1, 2 Org2)
   - Whether it is an error is decided by a weighted coin flip: `random() < error_rate`
   - RSSI and SNR are sampled from a Gaussian distribution using each profile's mean and standard deviation, then clamped to physically realistic ranges
   - The degrading gateway interpolates all three parameters linearly from good to bad based on round progress
2. Each event is formatted as a TTN uplink payload and POSTed to the webhook listener
3. `/admin/flush` is called to force the aggregator to submit all batches to the blockchain
4. A 2-second sleep allows Fabric transactions to commit in separate blocks (avoids MVCC conflicts)
5. `ComputeTrustScore` is called for each gateway and the result recorded to CSV
6. Pending billing charges between org pairs are queried and recorded to CSV

The random seed is fixed at 42, making the entire run **deterministic and reproducible**.

Results are written to `results/trust_scores.csv`, `results/latencies.csv`, `results/billing.csv`, and `results/events.csv`.

---

## Key design decisions and their reasons

| Decision | Why |
|---|---|
| Permissioned blockchain (Fabric) not public chain | No cryptocurrency needed; participants are known organisations; transaction throughput is predictable |
| Aggregation before blockchain writes | Writing every packet individually would produce thousands of transactions per hour; aggregation reduces this to one per gateway per time window |
| Peer CLI for blockchain calls, not Go SDK | Simpler integration from Python; no need to embed a Fabric SDK; acceptable latency for batch operations |
| 60% reliability / 40% signal weighting | Reliability (error rate) is operator-controllable — a gateway that drops packets is a trust violation. Signal quality is partly geography and hardware, so weighted lower |
| 30-day decay half-life | Recent behaviour dominates; a gateway that was unreliable last month but improved this week recovers its score within weeks rather than months |
| Home network defines billing policy | The device owner pre-commits publicly on-chain to their roaming rates. All participants can see what any org has agreed to pay — transparency without a central authority |
| MySQL alongside blockchain | Blockchain is the authority; MySQL is the fast read replica for the dashboard. Avoids querying the blockchain on every page load |
| Off-chain settlement payments | Blockchain records the obligation and the confirmation; actual fund transfers use existing banking rails. The blockchain is the receipt, not the payment processor |

---

## Port reference

| Service | Port | Purpose |
|---|---|---|
| Webhook Listener | 8000 | Receives TTN webhooks, exposes admin and metrics endpoints |
| Next.js Dashboard | 3000 | Operator UI |
| Prometheus | 9090 | Metrics collection |
| MySQL | 3307 | Event cache and audit trail |
| phpMyAdmin | 8080 | Database management UI |
| Grafana (optional) | 3001 | Time-series visualisation |
| Fabric Peer Org1 | 7051 | Blockchain peer node |
| Fabric Peer Org2 | 9051 | Blockchain peer node |
| Fabric Orderer | 7050 | Transaction ordering |

---

## Project file structure

```
├── chaincode/
│   ├── trustmanagement/trustmanagement.go   # Gateway registry + trust scores
│   └── billing/billing.go                   # Policies, charges, settlements
│
├── webhook-listener/app/
│   ├── main.py                              # FastAPI app, startup, lifespan
│   ├── config.py                            # Environment configuration
│   ├── models/ttn_events.py                 # Pydantic models for TTN payloads
│   ├── routers/
│   │   ├── webhooks.py                      # /webhook/uplink, /join, /downlink
│   │   └── dashboard.py                     # Dashboard API endpoints
│   └── services/
│       ├── aggregator.py                    # Per-gateway event buffering
│       ├── fabric_client.py                 # peer CLI wrapper
│       └── database.py                      # MySQL write/read
│
├── scripts/
│   ├── simulate.py                          # 800-event evaluation simulation
│   ├── analyze.py                           # Results analysis + chart generation
│   ├── attack_demo.py                       # Byzantine gateway attack scenario
│   └── fabric_helper.py                     # Shared Fabric invoke helpers
│
├── results/                                 # CSVs and PNG charts from simulation
├── config/
│   ├── mysql/init.sql                       # Database schema
│   └── prometheus/prometheus.yml            # Scrape configuration
│
├── docker-compose.yml                       # MySQL, listener, Prometheus, dashboard
└── PROJECT_OVERVIEW.md                      # This document
```
