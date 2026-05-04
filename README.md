```
================================================================================
  Using Blockchain to Build Decentralised LoRaWAN Networks
  B.Sc. Computer Engineering Capstone Project — Ashesi University, 2026
  Author: Shadrack Nti
================================================================================

GitHub Repository
-----------------
  https://github.com/ShadrackAgyei/Blockchain-in-LoRaWAN

  (All source code, configuration files, scripts, and evaluation datasets
  are available in the repository above.)


--------------------------------------------------------------------------------
SYSTEM OVERVIEW
--------------------------------------------------------------------------------

This project implements a blockchain-based trust management and billing
framework for shared LoRaWAN infrastructure. It enables multiple organisations
to share LoRaWAN gateways with verifiable trust scores and automated inter-
organisation billing, without relying on a central authority.

The system consists of five main components:

  1. Hyperledger Fabric blockchain (2-organisation permissioned network)
  2. Go chaincodes: TrustManagement and Billing
  3. Python FastAPI webhook listener (bridges TTN events to the blockchain)
  4. MySQL database (event cache and audit trail)
  5. Next.js monitoring dashboard


--------------------------------------------------------------------------------
PREREQUISITES
--------------------------------------------------------------------------------

Software dependencies (install before proceeding):

  - Docker Desktop >= 24.0          https://docs.docker.com/get-docker/
  - Docker Compose >= 2.20
  - Go >= 1.21                      https://go.dev/dl/
  - Node.js >= 18 and npm           https://nodejs.org/
  - Python >= 3.10                  https://www.python.org/
  - curl, git, jq, make (standard Unix tools)

Hyperledger Fabric binaries and Docker images:

  curl -sSLO https://raw.githubusercontent.com/hyperledger/fabric/main/scripts/install-fabric.sh
  chmod +x install-fabric.sh
  ./install-fabric.sh docker samples binary

  This installs fabric-samples to ~/fabric-samples and pulls the required
  Docker images (peer, orderer, ca, ccenv, baseos, tools).

Hardware (for full physical deployment — optional for software-only demo):

  - Raspberry Pi 5 with RAK5146 LoRa concentrator and Pi HAT
  - ESP32 + LoRa module end devices
  - See documentation/hardware_setup.txt for wiring and firmware details.


--------------------------------------------------------------------------------
INSTALLATION
--------------------------------------------------------------------------------

1. Clone the repository
   ---------------------
   git clone https://github.com/ShadrackAgyei/big-brain-moment.git
   cd big-brain-moment

2. Configure environment variables
   ---------------------------------
   cp .env.example .env
   # Edit .env and set TTN_WEBHOOK_SECRET to match your TTN application's
   # webhook secret. The default MySQL credentials may be left as-is for
   # development.

3. Install Python dependencies (webhook listener)
   -------------------------------------------------
   cd webhook-listener
   python3 -m venv venv
   source venv/bin/activate          # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   cd ..

4. Install Node.js dependencies (dashboard)
   ------------------------------------------
   cd frontend
   npm install
   cp .env.local.example .env.local   # Edit if the API base URL differs
   cd ..


--------------------------------------------------------------------------------
DEPLOYMENT
--------------------------------------------------------------------------------

Step 1 — Start the Hyperledger Fabric network
----------------------------------------------
  ./scripts/setup-fabric-network.sh

  This creates a two-organisation network (Org1 and Org2) with a single
  orderer using Raft consensus, creates the channel "lorawan-channel", and
  joins both peers. The network uses the fabric-samples test-network layout.

  Expected output: "Channel 'lorawan-channel' joined successfully"

Step 2 — Deploy the chaincodes
--------------------------------
  ./scripts/deploy-chaincode.sh

  Deploys both the TrustManagement and Billing chaincodes as Chaincode-as-a-
  Service (CCaaS) containers. Both chaincodes are packaged, installed,
  approved by both organisations, and committed to the channel.

  Optional flags:
    --sequence N    chaincode sequence number (default: 1)
    --version V     chaincode version string (default: 1.0)

  Expected output: "Chaincode committed successfully on lorawan-channel"

Step 3 — Start supporting services
------------------------------------
  docker-compose up -d

  Starts MySQL (port 3307), the webhook listener (port 8000), Prometheus
  (port 9090), and Grafana (port 3001). The webhook listener runs in Docker
  for services only; for full blockchain integration it must also have network
  access to the Fabric peer (see note below).

  NOTE: The webhook listener inside Docker cannot directly reach the Fabric
  peer binary. For full end-to-end blockchain integration, run the listener
  on the host:

    cd webhook-listener
    source venv/bin/activate
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

Step 4 — Start the dashboard
------------------------------
  cd frontend
  npm run dev

  The Next.js dashboard is available at http://localhost:3000

Step 5 — (Optional) Run the demonstration test suite
------------------------------------------------------
  ./scripts/test-demo.sh

  Registers gateways, records forwarding batches, computes trust scores,
  creates billing policies, records charges, and initiates a settlement —
  exercising the full system end-to-end.


--------------------------------------------------------------------------------
DIRECTORY STRUCTURE
--------------------------------------------------------------------------------

  chaincode/
    trustmanagement/    Gateway registration, forwarding records, trust scores
    billing/            Billing policies, charge accumulation, settlement
  webhook-listener/
    app/
      main.py           FastAPI application entry point
      config.py         Environment-driven configuration
      models/           Pydantic models for TTN webhook payloads
      routers/          HTTP endpoints (/webhook, /health, /metrics)
      services/         Aggregator, Fabric client, database layer
  frontend/             Next.js monitoring dashboard
  config/
    mysql/              Database schema initialisation
  scripts/              Automation scripts (setup, deploy, test)
  results/              Evaluation output (CSVs, charts)
  docker-compose.yml    Full-stack container orchestration
  .env.example          Environment variable template


--------------------------------------------------------------------------------
CHAINCODE QUICK REFERENCE
--------------------------------------------------------------------------------

TrustManagement functions:
  RegisterGateway        Register a gateway with EUI, location, owner org
  UpdateGatewayStatus    Activate or suspend a gateway
  RecordForwardingBatch  Store an aggregated batch of forwarding events
  ComputeTrustScore      Calculate trust score from forwarding history
  GetTrustedGateways     Query all gateways above a minimum trust threshold

Billing functions:
  CreatePolicy           Define billing terms for a set of devices
  RecordCharge           Accumulate a charge for a roaming packet
  GetPendingCharges      Query outstanding charges between two organisations
  InitiateSettlement     Create a settlement proposal
  ConfirmPayment         Mark a settlement as paid

Invoke example (via Fabric peer CLI):
  peer chaincode invoke -o localhost:7050 \
    --ordererTLSHostnameOverride orderer.example.com \
    --tls --cafile $ORDERER_CA \
    -C lorawan-channel -n trust \
    -c '{"function":"RegisterGateway","Args":["GW001","eui-aabbccddaabbccdd","0.0,0.0","Org1MSP"]}'


--------------------------------------------------------------------------------
KNOWN ISSUES AND WORKAROUNDS
--------------------------------------------------------------------------------

  1. Docker Desktop broken pipe
     Fabric peers require DOCKER_SOCK=/var/run/docker.sock when starting via
     Docker Compose, otherwise chaincode builds fail with a broken pipe error.
     This is set in docker-compose.yml.

  2. Fabric MVCC conflicts
     Back-to-back invoke calls that read and write the same ledger key must be
     separated by 2-3 seconds to land in different blocks. The test scripts
     include the necessary sleeps.

  3. Billing policy owner organisation
     CreatePolicy must be invoked with the correct MSP identity because the
     chaincode uses getCallerOrg(). Use Org2MSP credentials for Org2 devices.

  4. Composite key range queries
     Use GetStateByPartialCompositeKey, not GetStateByRange, for composite-
     keyed records. Range queries with null-byte prefixes cause crashes.


--------------------------------------------------------------------------------
MONITORING
--------------------------------------------------------------------------------
  Webhook health:     http://localhost:8000/webhook/health
  Webhook metrics:    http://localhost:8000/metrics



--------------------------------------------------------------------------------
FURTHER DOCUMENTATION
--------------------------------------------------------------------------------

  documentation/user_manual.txt      Operational guide for day-to-day use
  documentation/hardware_setup.txt   Physical gateway and end-device setup
  documentation/api_reference.txt    Webhook listener REST API reference
  HARDWARE_SETUP.md                  Detailed RPi + RAK5146 wiring guide
  PROJECT_OVERVIEW.md                Full architecture description


--------------------------------------------------------------------------------
CONTACT
--------------------------------------------------------------------------------

  Shadrack Nti
  B.Sc. Computer Engineering, Ashesi University
  Email: shadrack.nti@ashesi.edu.gh
  Supervisor: Dr. Nathan Amanquah

================================================================================
```
