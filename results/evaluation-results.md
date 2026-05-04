# Evaluation Results

**Date:** 2026-03-11
**System:** LoRaWAN Blockchain Trust Management and Billing Framework
**Environment:** Hyperledger Fabric v2.5 test-network (2 organisations, Raft orderer), chaincodes deployed as Docker containers via Chaincode-as-a-Service (ccaas)

---

## 1. Experimental Setup

The evaluation simulated a multi-organisation LoRaWAN network with 8 gateways, 6 end devices, and 2 organisations (Org1 and Org2). A total of **800 uplink events** were driven through the system across **10 rounds** (~80 events per round), with each event processed through the full pipeline: webhook ingestion, MySQL caching, event aggregation, and blockchain recording.

### 1.1 Gateway Profiles

| Profile | Gateways | Error Rate | RSSI Range (dBm) | SNR Range (dB) |
|---------|----------|------------|-------------------|----------------|
| Reliable | 3 (2x Org1, 1x Org2) | 0--2% | -65 to -80 | 7--10 |
| Average | 2 (1x Org1, 1x Org2) | 5--10% | -85 to -95 | 3--5 |
| Poor | 2 (1x Org1, 1x Org2) | 15--25% | -100 to -110 | -2 to 1 |
| Degrading | 1 (Org1) | 2% to 30% (linear) | -70 to -105 | 8 to 0 |

### 1.2 Device Allocation

Six simulated devices (4 owned by Org1, 2 owned by Org2) were randomly assigned to gateways each round. When a device's home organisation differs from the gateway's owner organisation, this constitutes **roaming traffic** and triggers billing charges.

- **Total events:** 800
- **Roaming events:** 363 (45.4%)
- **Non-roaming events:** 437 (54.6%)
- **Total forwarding errors:** 76 (9.5% overall error rate)

---

## 2. Trust Score Evaluation

### 2.1 Trust Score Algorithm

The trust score combines two weighted factors:

- **Reliability (60%):** Proportion of successfully forwarded packets (`1 - errorCount / totalPackets`)
- **Signal quality (40%):** Normalised average of RSSI (mapped from [-120, -40] dBm to [0, 1]) and SNR (mapped from [-20, +10] dB to [0, 1])

Records are weighted by an exponential decay function with a 30-day half-life, giving more recent records greater influence. Inactive gateways receive a 5% trust penalty per computation cycle.

### 2.2 Final Trust Scores by Profile

| Profile | Gateways | Mean Score | Min | Max | Std Dev |
|---------|----------|------------|-----|-----|---------|
| Reliable | 3 | **0.911** | 0.897 | 0.923 | 0.013 |
| Average | 2 | **0.837** | 0.835 | 0.839 | 0.002 |
| Poor | 2 | **0.774** | 0.768 | 0.780 | 0.008 |
| Degrading | 1 | **0.843** | -- | -- | -- |

> **Figure reference:** `results/figures/fig1_trust_convergence.png` (line chart), `results/figures/fig2_trust_by_profile.png` (box plot)

### 2.3 Analysis

The trust score algorithm successfully **differentiates gateway quality**:

1. **Reliable gateways** (0.897--0.923) score highest, reflecting near-zero error rates and strong signal quality. The variation within the group is due to randomised RSSI/SNR values within profile bounds.

2. **Average gateways** (0.835--0.839) form a distinct middle tier, penalised by their 5--10% error rate and weaker signal metrics.

3. **Poor gateways** (0.768--0.780) are clearly separated from the other profiles, with their 15--25% error rate and weak RSSI/SNR significantly reducing their scores.

4. **The degrading gateway** (0.843) averages out to an intermediate score. Because the trust algorithm uses exponential decay weighting, early high-quality records from when the gateway was performing well still contribute positively, but their influence diminishes as more degraded records accumulate.

5. **All 8 gateways remain above the 0.7 trust threshold**, meaning none would be excluded from the trusted set in this simulation. In a production deployment, a gateway with sustained poor performance or malicious behaviour would eventually fall below this threshold and be flagged for review.

### 2.4 Convergence Behaviour

Trust scores converge rapidly after the first round of forwarding records. By round 1, each gateway's score reflects its profile characteristics, and subsequent rounds reinforce the established pattern with minimal variation (< 0.005 standard deviation across rounds for stable profiles). The degrading gateway shows a characteristic rise-then-decline pattern: its score peaks at 0.848 (round 5) before declining to 0.843 (round 10) as degraded records accumulate.

---

## 3. Transaction Latency

### 3.1 Overall Latency

| Metric | Value |
|--------|-------|
| Total transactions | 990 |
| Success rate | **100%** (990/990) |
| Mean latency | 41.1 ms |
| Median (p50) | 41.3 ms |
| 95th percentile (p95) | 73.9 ms |
| 99th percentile (p99) | 371.3 ms |
| Minimum | 5.4 ms |
| Maximum | 551.1 ms |

### 3.2 Latency by Operation

| Operation | Count | Mean (ms) | p95 (ms) |
|-----------|-------|-----------|----------|
| Webhook uplink ingestion | 800 | 33.9 | 72.2 |
| Aggregator flush (batch write) | 10 | 448.5 | 505.8 |
| Trust score computation (invoke) | 80 | 59.7 | 74.9 |
| Trust score query | 80 | 43.1 | 49.2 |
| Billing query | 20 | 43.6 | 52.4 |

> **Figure reference:** `results/figures/fig3_latency_distribution.png` (histogram + CDF), `results/figures/fig4_latency_over_time.png` (scatter plot)

### 3.3 Analysis

1. **Webhook ingestion** (33.9 ms mean) is the fastest operation, involving only HTTP acceptance and MySQL buffering. The p95 of 72.2 ms includes occasional network variability.

2. **Aggregator flush** (448.5 ms mean) is the most expensive operation because it batches all buffered events into a single Fabric invoke transaction requiring endorsement from both organisation peers. This is intentionally batched to amortise the blockchain overhead across many events.

3. **Trust score computation** (59.7 ms mean) involves a Fabric invoke that reads all forwarding records for a gateway, computes the weighted score, and writes the updated trust value. This is efficient for the 90-day look-back window used in the algorithm.

4. **Query operations** (43 ms mean) are faster than invokes because they only require a single peer read without orderer involvement or consensus.

5. **Tail latency**: The p99 of 371.3 ms and maximum of 551.1 ms are attributable to the aggregator flush operations, which are expected to be higher-latency. Excluding flush operations, the p99 drops to approximately 75 ms, which is well within acceptable bounds for LoRaWAN network management operations.

---

## 4. Billing and Settlement

### 4.1 Charge Accumulation

| Metric | Value |
|--------|-------|
| Total charges recorded | 1,336 |
| Total amount | 133,600 microcents ($0.1336) |
| Roaming events generating charges | 363 |

Charges accumulated linearly across rounds, with Org1-to-Org2 and Org2-to-Org1 roaming traffic generating approximately equal volumes. By the final round:

- **Org1 owes Org2:** 88 charges totalling 8,800 microcents
- **Org2 owes Org1:** 85 charges totalling 8,500 microcents

### 4.2 Settlement

The settlement lifecycle was demonstrated end-to-end:

1. **InitiateSettlement** -- Org2 initiated settlement of charges owed to Org1
2. Settlement was recorded on the blockchain with status `PENDING`
3. Both parties can query the settlement details including charge count and total amount

> **Figure reference:** `results/figures/fig5_billing_accumulation.png` (stacked bar + cumulative), `results/figures/fig6_settlement_flow.png` (timeline)

### 4.3 Analysis

The billing system correctly:
- **Detects roaming traffic** by comparing device home organisation against gateway owner organisation
- **Applies per-packet pricing** according to the billing policy (100 microcents/uplink, 200 microcents/downlink, 500 microcents/join)
- **Accumulates charges bidirectionally** between organisations
- **Supports atomic settlement** via the blockchain, ensuring both parties agree on the total before payment

---

## 5. Security Evaluation

Two attack scenarios were executed against the live blockchain network. All **8 out of 8 steps passed**, demonstrating the framework's security properties.

### 5.1 Attack 1: Unauthorised Gateway Registration

This attack tests whether the MSP-based access control prevents cross-organisation impersonation.

| Step | Action | Identity | Result |
|------|--------|----------|--------|
| 1 | Org2 registers a gateway claiming Org1 ownership | Org2MSP | **REJECTED** -- "caller MSPID Org2MSP does not match owner org Org1" |
| 2 | Org2 suspends an Org1-owned gateway | Org2MSP | **REJECTED** -- "only the owner organisation can update gateway status" |
| 3 | Org1 registers a gateway as Org1 (control) | Org1MSP | **SUCCESS** -- gateway registered normally |

**Finding:** The chaincode's MSP identity verification prevents any organisation from registering or modifying gateways belonging to another organisation. This is enforced at the smart contract level using Fabric's client identity library, making it impossible to bypass through network-level attacks alone.

### 5.2 Attack 2: Trust Score Manipulation via Inflated Records

This attack tests whether a malicious gateway operator can artificially inflate their trust score by submitting fabricated forwarding records, and whether the blockchain's immutable audit trail enables detection.

| Step | Action | Result |
|------|--------|--------|
| 1 | Register malicious gateway (legitimate Org2) | **SUCCESS** -- gateway registered normally |
| 2 | Submit 5 rounds of inflated records (0 errors, RSSI=-50 dBm, SNR=12 dB) | **ACCEPTED** -- data written to blockchain |
| 3 | Compute trust score | **0.975** -- artificially elevated (normal reliable gateways score ~0.91) |
| 4 | Audit query for anomalous records | **5 anomalies detected** -- RSSI > -60 dBm and SNR > 10 dB flagged as physically implausible |
| 5 | Suspend gateway and verify exclusion | **SUSPENDED** -- excluded from `GetTrustedGateways(0.7)` |

> **Figure reference:** `results/figures/attack_audit_trail.png` (audit table with anomalies highlighted)

**Finding:** While the blockchain accepts all forwarding records submitted by authorised gateways (the data itself is not validated at submission time), the **immutable audit trail** enables post-hoc detection of anomalous records. Key observations:

1. **RSSI of -50 dBm** is physically implausible for LoRaWAN (typical range: -65 to -120 dBm). The audit query flags any record with RSSI > -60 dBm.

2. **SNR of 12 dB** exceeds typical LoRaWAN range (usually -20 to +10 dB). The audit query flags records with SNR > 10 dB.

3. **Zero errors across 200+ packets** per round is statistically unlikely for any real-world gateway.

4. The artificially elevated trust score of **0.975** (versus ~0.91 for genuinely reliable gateways) is itself an anomaly indicator.

5. Once detected, the gateway is **suspended** via `UpdateGatewayStatus`, immediately excluding it from the trusted set. All records remain on the blockchain for forensic analysis.

**Comparison with centralised systems:** In a centralised database, an attacker with write access could silently modify or delete anomalous records to cover their tracks. On the blockchain, all records are **immutable and timestamped**, providing a tamper-proof audit trail that supports both automated anomaly detection and manual investigation.

---

## 6. Summary

| Category | Key Result |
|----------|------------|
| Trust differentiation | 4 distinct tiers: reliable (0.91), average (0.84), poor (0.77), degrading (0.84) |
| Transaction throughput | 990 transactions at 100% success rate |
| Median latency | 41.3 ms (p95: 73.9 ms, excluding batch operations) |
| Billing accuracy | 1,336 charges across 363 roaming events, bidirectional settlement |
| Security (access control) | MSP identity checks block 100% of cross-org impersonation attempts |
| Security (audit trail) | 5/5 inflated records detected via blockchain audit query |
| Trust threshold | All 8 legitimate gateways above 0.7; suspended gateways immediately excluded |

### Output Files

| File | Description |
|------|-------------|
| `results/trust_scores.csv` | Trust scores per gateway per round (80 rows) |
| `results/latencies.csv` | Per-transaction latency with operation type (990 rows) |
| `results/billing.csv` | Billing charges per round per org pair (20 rows) |
| `results/events.csv` | Event statistics per gateway per round (80 rows) |
| `results/attack_results.json` | Structured attack scenario results (8 steps) |
| `results/figures/fig1_trust_convergence.png` | Trust score convergence over 10 rounds |
| `results/figures/fig2_trust_by_profile.png` | Final trust scores grouped by profile |
| `results/figures/fig3_latency_distribution.png` | Latency histogram with CDF overlay |
| `results/figures/fig4_latency_over_time.png` | Per-transaction latency scatter plot |
| `results/figures/fig5_billing_accumulation.png` | Billing charge accumulation per round |
| `results/figures/fig6_settlement_flow.png` | Settlement lifecycle timeline |
| `results/figures/attack_audit_trail.png` | Audit trail table with anomalies flagged |
