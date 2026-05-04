package main

import (
	"encoding/json"
	"fmt"
	"math"
	"sort"
	"time"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

// TrustManagementContract provides functions for managing gateway trust
type TrustManagementContract struct {
	contractapi.Contract
}

// GeoLocation represents geographic coordinates
type GeoLocation struct {
	Latitude  float64 `json:"latitude"`
	Longitude float64 `json:"longitude"`
	Altitude  float64 `json:"altitude"`
}

// Gateway represents a LoRaWAN gateway in the network
type Gateway struct {
	GatewayEUI   string      `json:"gatewayEUI"`
	OwnerOrg     string      `json:"ownerOrg"`
	Location     GeoLocation `json:"location"`
	Status       string      `json:"status"`      // ACTIVE, SUSPENDED
	TrustScore   float64     `json:"trustScore"`  // 0.0-1.0
	RegisteredAt int64       `json:"registeredAt"`
	LastUpdated  int64       `json:"lastUpdated"`
}

// ForwardingRecord represents aggregated forwarding statistics for a gateway
type ForwardingRecord struct {
	RecordID      string  `json:"recordID"`
	GatewayEUI    string  `json:"gatewayEUI"`
	PeriodStart   int64   `json:"periodStart"`
	PeriodEnd     int64   `json:"periodEnd"`
	UplinkCount   int     `json:"uplinkCount"`
	DownlinkCount int     `json:"downlinkCount"`
	JoinCount     int     `json:"joinCount"`
	ErrorCount    int     `json:"errorCount"`
	AvgRSSI       float64 `json:"avgRSSI"`
	AvgSNR        float64 `json:"avgSNR"`
}

// TrustScoreConfig holds the parameters for trust score calculation
type TrustScoreConfig struct {
	ReliabilityWeight float64 `json:"reliabilityWeight"` // 0.6
	SignalWeight      float64 `json:"signalWeight"`      // 0.4
	DecayHalfLifeDays int     `json:"decayHalfLifeDays"` // 30
	InactivityPenalty float64 `json:"inactivityPenalty"` // 0.05
	InactivityDays    int     `json:"inactivityDays"`    // 7
}

// DefaultTrustConfig returns the default trust score configuration
func DefaultTrustConfig() TrustScoreConfig {
	return TrustScoreConfig{
		ReliabilityWeight: 0.6,
		SignalWeight:      0.4,
		DecayHalfLifeDays: 30,
		InactivityPenalty: 0.05,
		InactivityDays:    7,
	}
}

// InitLedger initializes the chaincode with default configuration
func (c *TrustManagementContract) InitLedger(ctx contractapi.TransactionContextInterface) error {
	config := DefaultTrustConfig()
	configJSON, err := json.Marshal(config)
	if err != nil {
		return fmt.Errorf("failed to marshal config: %v", err)
	}

	return ctx.GetStub().PutState("TRUST_CONFIG", configJSON)
}

// RegisterGateway registers a new gateway with the network
func (c *TrustManagementContract) RegisterGateway(
	ctx contractapi.TransactionContextInterface,
	gatewayEUI string,
	ownerOrg string,
	latitude float64,
	longitude float64,
	altitude float64,
) error {
	// Check if gateway already exists
	existing, err := ctx.GetStub().GetState(gatewayKey(gatewayEUI))
	if err != nil {
		return fmt.Errorf("failed to read gateway: %v", err)
	}
	if existing != nil {
		return fmt.Errorf("gateway %s already exists", gatewayEUI)
	}

	// Verify caller belongs to owner org (MSP check)
	clientMSPID, err := ctx.GetClientIdentity().GetMSPID()
	if err != nil {
		return fmt.Errorf("failed to get client MSPID: %v", err)
	}
	if clientMSPID != ownerOrg+"MSP" {
		return fmt.Errorf("caller MSPID %s does not match owner org %s", clientMSPID, ownerOrg)
	}

	now := time.Now().Unix()
	gateway := Gateway{
		GatewayEUI: gatewayEUI,
		OwnerOrg:   ownerOrg,
		Location: GeoLocation{
			Latitude:  latitude,
			Longitude: longitude,
			Altitude:  altitude,
		},
		Status:       "ACTIVE",
		TrustScore:   0.5, // Initial neutral trust score
		RegisteredAt: now,
		LastUpdated:  now,
	}

	gatewayJSON, err := json.Marshal(gateway)
	if err != nil {
		return fmt.Errorf("failed to marshal gateway: %v", err)
	}

	// Store gateway
	if err := ctx.GetStub().PutState(gatewayKey(gatewayEUI), gatewayJSON); err != nil {
		return fmt.Errorf("failed to store gateway: %v", err)
	}

	// Add to org index for efficient queries
	indexKey, err := ctx.GetStub().CreateCompositeKey("org~gateway", []string{ownerOrg, gatewayEUI})
	if err != nil {
		return fmt.Errorf("failed to create composite key: %v", err)
	}
	if err := ctx.GetStub().PutState(indexKey, []byte{0x00}); err != nil {
		return fmt.Errorf("failed to store org index: %v", err)
	}

	return nil
}

// UpdateGatewayStatus updates the status of a gateway (ACTIVE/SUSPENDED)
func (c *TrustManagementContract) UpdateGatewayStatus(
	ctx contractapi.TransactionContextInterface,
	gatewayEUI string,
	newStatus string,
) error {
	if newStatus != "ACTIVE" && newStatus != "SUSPENDED" {
		return fmt.Errorf("invalid status: %s (must be ACTIVE or SUSPENDED)", newStatus)
	}

	gateway, err := c.getGateway(ctx, gatewayEUI)
	if err != nil {
		return err
	}

	// Verify caller owns this gateway
	clientMSPID, err := ctx.GetClientIdentity().GetMSPID()
	if err != nil {
		return fmt.Errorf("failed to get client MSPID: %v", err)
	}
	if clientMSPID != gateway.OwnerOrg+"MSP" {
		return fmt.Errorf("only owner org can update gateway status")
	}

	gateway.Status = newStatus
	gateway.LastUpdated = time.Now().Unix()

	return c.saveGateway(ctx, gateway)
}

// RecordForwardingBatch stores aggregated forwarding events from the webhook listener
func (c *TrustManagementContract) RecordForwardingBatch(
	ctx contractapi.TransactionContextInterface,
	gatewayEUI string,
	periodStart int64,
	periodEnd int64,
	uplinkCount int,
	downlinkCount int,
	joinCount int,
	errorCount int,
	avgRSSI float64,
	avgSNR float64,
) error {
	// Verify gateway exists
	gateway, err := c.getGateway(ctx, gatewayEUI)
	if err != nil {
		return err
	}

	// Generate record ID
	txID := ctx.GetStub().GetTxID()
	recordID := fmt.Sprintf("FR_%s_%d", gatewayEUI, periodStart)

	record := ForwardingRecord{
		RecordID:      recordID,
		GatewayEUI:    gatewayEUI,
		PeriodStart:   periodStart,
		PeriodEnd:     periodEnd,
		UplinkCount:   uplinkCount,
		DownlinkCount: downlinkCount,
		JoinCount:     joinCount,
		ErrorCount:    errorCount,
		AvgRSSI:       avgRSSI,
		AvgSNR:        avgSNR,
	}

	recordJSON, err := json.Marshal(record)
	if err != nil {
		return fmt.Errorf("failed to marshal record: %v", err)
	}

	// Store the record
	recordKey := fmt.Sprintf("RECORD_%s", recordID)
	if err := ctx.GetStub().PutState(recordKey, recordJSON); err != nil {
		return fmt.Errorf("failed to store record: %v", err)
	}

	// Create composite key for time-based queries
	timeKey, err := ctx.GetStub().CreateCompositeKey("gateway~time", []string{
		gatewayEUI,
		fmt.Sprintf("%020d", periodStart),
	})
	if err != nil {
		return fmt.Errorf("failed to create time composite key: %v", err)
	}
	if err := ctx.GetStub().PutState(timeKey, []byte(recordID)); err != nil {
		return fmt.Errorf("failed to store time index: %v", err)
	}

	// Update gateway last updated timestamp
	gateway.LastUpdated = time.Now().Unix()
	if err := c.saveGateway(ctx, gateway); err != nil {
		return fmt.Errorf("failed to update gateway: %v", err)
	}

	// Emit event for monitoring
	eventPayload := map[string]interface{}{
		"txID":        txID,
		"gatewayEUI":  gatewayEUI,
		"recordID":    recordID,
		"uplinkCount": uplinkCount,
	}
	eventJSON, _ := json.Marshal(eventPayload)
	ctx.GetStub().SetEvent("ForwardingRecorded", eventJSON)

	return nil
}

// ComputeTrustScore calculates and updates the trust score for a gateway
func (c *TrustManagementContract) ComputeTrustScore(
	ctx contractapi.TransactionContextInterface,
	gatewayEUI string,
) (float64, error) {
	gateway, err := c.getGateway(ctx, gatewayEUI)
	if err != nil {
		return 0, err
	}

	config, err := c.getTrustConfig(ctx)
	if err != nil {
		return 0, err
	}

	// Get recent forwarding records (last 90 days)
	now := time.Now().Unix()
	cutoff := now - (90 * 24 * 60 * 60)
	records, err := c.getForwardingRecords(ctx, gatewayEUI, cutoff, now)
	if err != nil {
		return 0, err
	}

	if len(records) == 0 {
		// Apply inactivity penalty
		gateway.TrustScore = math.Max(0, gateway.TrustScore-config.InactivityPenalty)
		if err := c.saveGateway(ctx, gateway); err != nil {
			return 0, err
		}
		return gateway.TrustScore, nil
	}

	// Calculate weighted trust score with exponential decay
	var totalWeight float64
	var weightedReliability float64
	var weightedSignal float64

	halfLifeSeconds := float64(config.DecayHalfLifeDays * 24 * 60 * 60)

	for _, record := range records {
		// Calculate age-based decay weight
		age := float64(now - record.PeriodEnd)
		decayWeight := math.Pow(0.5, age/halfLifeSeconds)

		totalPackets := record.UplinkCount + record.DownlinkCount + record.JoinCount
		if totalPackets == 0 {
			continue
		}

		// Reliability: percentage of successful packets
		reliability := 1.0 - (float64(record.ErrorCount) / float64(totalPackets+record.ErrorCount))

		// Signal quality: normalize RSSI (-120 to -40 dBm) and SNR (-20 to +10 dB)
		rssiNorm := math.Min(1, math.Max(0, (record.AvgRSSI+120)/80))
		snrNorm := math.Min(1, math.Max(0, (record.AvgSNR+20)/30))
		signalQuality := (rssiNorm + snrNorm) / 2

		weightedReliability += reliability * decayWeight
		weightedSignal += signalQuality * decayWeight
		totalWeight += decayWeight
	}

	if totalWeight > 0 {
		avgReliability := weightedReliability / totalWeight
		avgSignal := weightedSignal / totalWeight

		// Combined trust score
		trustScore := (config.ReliabilityWeight * avgReliability) + (config.SignalWeight * avgSignal)

		// Check for recent inactivity
		lastRecord := records[len(records)-1]
		daysSinceLastRecord := float64(now-lastRecord.PeriodEnd) / (24 * 60 * 60)
		if daysSinceLastRecord > float64(config.InactivityDays) {
			trustScore = math.Max(0, trustScore-config.InactivityPenalty)
		}

		gateway.TrustScore = math.Min(1, math.Max(0, trustScore))
	}

	gateway.LastUpdated = now
	if err := c.saveGateway(ctx, gateway); err != nil {
		return 0, err
	}

	return gateway.TrustScore, nil
}

// GetTrustedGateways returns all gateways with trust score above the threshold
func (c *TrustManagementContract) GetTrustedGateways(
	ctx contractapi.TransactionContextInterface,
	minTrustScore float64,
) ([]*Gateway, error) {
	if minTrustScore < 0 || minTrustScore > 1 {
		return nil, fmt.Errorf("minTrustScore must be between 0 and 1")
	}

	// Query all gateways
	iterator, err := ctx.GetStub().GetStateByRange("GATEWAY_", "GATEWAY_~")
	if err != nil {
		return nil, fmt.Errorf("failed to get gateways: %v", err)
	}
	defer iterator.Close()

	var trustedGateways []*Gateway

	for iterator.HasNext() {
		result, err := iterator.Next()
		if err != nil {
			return nil, fmt.Errorf("failed to iterate: %v", err)
		}

		var gateway Gateway
		if err := json.Unmarshal(result.Value, &gateway); err != nil {
			continue
		}

		if gateway.Status == "ACTIVE" && gateway.TrustScore >= minTrustScore {
			trustedGateways = append(trustedGateways, &gateway)
		}
	}

	// Sort by trust score descending
	sort.Slice(trustedGateways, func(i, j int) bool {
		return trustedGateways[i].TrustScore > trustedGateways[j].TrustScore
	})

	return trustedGateways, nil
}

// GetGateway retrieves a gateway by its EUI
func (c *TrustManagementContract) GetGateway(
	ctx contractapi.TransactionContextInterface,
	gatewayEUI string,
) (*Gateway, error) {
	return c.getGateway(ctx, gatewayEUI)
}

// GetGatewaysByOrg retrieves all gateways owned by an organization
func (c *TrustManagementContract) GetGatewaysByOrg(
	ctx contractapi.TransactionContextInterface,
	ownerOrg string,
) ([]*Gateway, error) {
	iterator, err := ctx.GetStub().GetStateByPartialCompositeKey("org~gateway", []string{ownerOrg})
	if err != nil {
		return nil, fmt.Errorf("failed to query by org: %v", err)
	}
	defer iterator.Close()

	var gateways []*Gateway

	for iterator.HasNext() {
		result, err := iterator.Next()
		if err != nil {
			return nil, fmt.Errorf("failed to iterate: %v", err)
		}

		_, compositeKeyParts, err := ctx.GetStub().SplitCompositeKey(result.Key)
		if err != nil {
			continue
		}

		if len(compositeKeyParts) >= 2 {
			gatewayEUI := compositeKeyParts[1]
			gateway, err := c.getGateway(ctx, gatewayEUI)
			if err == nil {
				gateways = append(gateways, gateway)
			}
		}
	}

	return gateways, nil
}

// GetForwardingHistory retrieves forwarding records for a gateway within a time range
func (c *TrustManagementContract) GetForwardingHistory(
	ctx contractapi.TransactionContextInterface,
	gatewayEUI string,
	startTime int64,
	endTime int64,
) ([]*ForwardingRecord, error) {
	records, err := c.getForwardingRecords(ctx, gatewayEUI, startTime, endTime)
	if err != nil {
		return nil, err
	}

	// Convert to pointer slice
	result := make([]*ForwardingRecord, len(records))
	for i := range records {
		result[i] = &records[i]
	}
	return result, nil
}

// Helper functions

func gatewayKey(gatewayEUI string) string {
	return fmt.Sprintf("GATEWAY_%s", gatewayEUI)
}

func (c *TrustManagementContract) getGateway(
	ctx contractapi.TransactionContextInterface,
	gatewayEUI string,
) (*Gateway, error) {
	gatewayJSON, err := ctx.GetStub().GetState(gatewayKey(gatewayEUI))
	if err != nil {
		return nil, fmt.Errorf("failed to read gateway: %v", err)
	}
	if gatewayJSON == nil {
		return nil, fmt.Errorf("gateway %s does not exist", gatewayEUI)
	}

	var gateway Gateway
	if err := json.Unmarshal(gatewayJSON, &gateway); err != nil {
		return nil, fmt.Errorf("failed to unmarshal gateway: %v", err)
	}

	return &gateway, nil
}

func (c *TrustManagementContract) saveGateway(
	ctx contractapi.TransactionContextInterface,
	gateway *Gateway,
) error {
	gatewayJSON, err := json.Marshal(gateway)
	if err != nil {
		return fmt.Errorf("failed to marshal gateway: %v", err)
	}

	return ctx.GetStub().PutState(gatewayKey(gateway.GatewayEUI), gatewayJSON)
}

func (c *TrustManagementContract) getTrustConfig(
	ctx contractapi.TransactionContextInterface,
) (*TrustScoreConfig, error) {
	configJSON, err := ctx.GetStub().GetState("TRUST_CONFIG")
	if err != nil {
		return nil, fmt.Errorf("failed to read config: %v", err)
	}
	if configJSON == nil {
		config := DefaultTrustConfig()
		return &config, nil
	}

	var config TrustScoreConfig
	if err := json.Unmarshal(configJSON, &config); err != nil {
		return nil, fmt.Errorf("failed to unmarshal config: %v", err)
	}

	return &config, nil
}

func (c *TrustManagementContract) getForwardingRecords(
	ctx contractapi.TransactionContextInterface,
	gatewayEUI string,
	startTime int64,
	endTime int64,
) ([]ForwardingRecord, error) {
	// Use GetStateByPartialCompositeKey (safe with null-byte prefixed keys)
	// then filter by time range in the loop
	iterator, err := ctx.GetStub().GetStateByPartialCompositeKey("gateway~time", []string{gatewayEUI})
	if err != nil {
		return nil, fmt.Errorf("failed to query records: %v", err)
	}
	defer iterator.Close()

	var records []ForwardingRecord

	for iterator.HasNext() {
		result, err := iterator.Next()
		if err != nil {
			return nil, fmt.Errorf("failed to iterate: %v", err)
		}

		recordID := string(result.Value)
		recordKey := fmt.Sprintf("RECORD_%s", recordID)
		recordJSON, err := ctx.GetStub().GetState(recordKey)
		if err != nil || recordJSON == nil {
			continue
		}

		var record ForwardingRecord
		if err := json.Unmarshal(recordJSON, &record); err != nil {
			continue
		}

		// Filter by time range
		if record.PeriodStart >= startTime && record.PeriodStart <= endTime {
			records = append(records, record)
		}
	}

	return records, nil
}

func main() {
	chaincode, err := contractapi.NewChaincode(&TrustManagementContract{})
	if err != nil {
		fmt.Printf("Error creating TrustManagement chaincode: %v\n", err)
		return
	}

	if err := chaincode.Start(); err != nil {
		fmt.Printf("Error starting TrustManagement chaincode: %v\n", err)
	}
}
