package main

import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

// BillingContract provides functions for managing billing and settlements
type BillingContract struct {
	contractapi.Contract
}

// PricingTier defines the pricing structure for different packet types
type PricingTier struct {
	UplinkMicro   int64 `json:"uplinkMicro"`   // Microcents per uplink packet
	DownlinkMicro int64 `json:"downlinkMicro"` // Microcents per downlink packet
	JoinMicro     int64 `json:"joinMicro"`     // Microcents per join request
}

// Policy defines billing terms for a set of devices
type Policy struct {
	PolicyID    string      `json:"policyID"`
	OwnerOrg    string      `json:"ownerOrg"`     // Home network that owns the devices
	Devices     []string    `json:"devices"`      // DevEUIs covered by this policy
	PacketTypes []string    `json:"packetTypes"`  // UPLINK, DOWNLINK, JOIN
	Pricing     PricingTier `json:"pricing"`
	ValidFrom   int64       `json:"validFrom"`
	ValidUntil  int64       `json:"validUntil"`
	Active      bool        `json:"active"`
	CreatedAt   int64       `json:"createdAt"`
}

// ChargeItem represents a single billing charge
type ChargeItem struct {
	ChargeID    string `json:"chargeID"`
	PolicyID    string `json:"policyID"`
	DevEUI      string `json:"devEUI"`
	GatewayEUI  string `json:"gatewayEUI"`
	PacketType  string `json:"packetType"` // UPLINK, DOWNLINK, JOIN
	PacketCount int    `json:"packetCount"`
	AmountMicro int64  `json:"amountMicro"`
	Timestamp   int64  `json:"timestamp"`
}

// ChargeAccumulator tracks charges between two organizations
type ChargeAccumulator struct {
	AccumulatorID string       `json:"accumulatorID"`
	DebtorOrg     string       `json:"debtorOrg"`   // Org that owes money (home network)
	CreditorOrg   string       `json:"creditorOrg"` // Org that is owed money (gateway owner)
	TotalMicro    int64        `json:"totalMicro"`
	Charges       []ChargeItem `json:"charges"`
	PeriodStart   int64        `json:"periodStart"`
	LastUpdated   int64        `json:"lastUpdated"`
}

// Settlement represents a settlement proposal between organizations
type Settlement struct {
	SettlementID  string `json:"settlementID"`
	DebtorOrg     string `json:"debtorOrg"`
	CreditorOrg   string `json:"creditorOrg"`
	TotalMicro    int64  `json:"totalMicro"`
	ChargeCount   int    `json:"chargeCount"`
	PeriodStart   int64  `json:"periodStart"`
	PeriodEnd     int64  `json:"periodEnd"`
	Status        string `json:"status"` // PENDING, PAID, DISPUTED, CANCELLED
	PaymentRef    string `json:"paymentRef"`
	CreatedAt     int64  `json:"createdAt"`
	ResolvedAt    int64  `json:"resolvedAt"`
	DisputeReason string `json:"disputeReason"`
}

// InitLedger initializes the billing chaincode
func (c *BillingContract) InitLedger(ctx contractapi.TransactionContextInterface) error {
	// Initialize with default pricing template
	defaultPricing := PricingTier{
		UplinkMicro:   100,  // 0.001 cents per uplink
		DownlinkMicro: 200,  // 0.002 cents per downlink
		JoinMicro:     500,  // 0.005 cents per join
	}

	pricingJSON, err := json.Marshal(defaultPricing)
	if err != nil {
		return fmt.Errorf("failed to marshal default pricing: %v", err)
	}

	return ctx.GetStub().PutState("DEFAULT_PRICING", pricingJSON)
}

// CreatePolicy creates a new billing policy for a set of devices
func (c *BillingContract) CreatePolicy(
	ctx contractapi.TransactionContextInterface,
	policyID string,
	devices []string,
	packetTypes []string,
	uplinkMicro int64,
	downlinkMicro int64,
	joinMicro int64,
	validUntil int64,
) error {
	// Check if policy already exists
	existing, err := ctx.GetStub().GetState(policyKey(policyID))
	if err != nil {
		return fmt.Errorf("failed to read policy: %v", err)
	}
	if existing != nil {
		return fmt.Errorf("policy %s already exists", policyID)
	}

	// Get caller's organization
	ownerOrg, err := c.getCallerOrg(ctx)
	if err != nil {
		return err
	}

	// Validate packet types
	validTypes := map[string]bool{"UPLINK": true, "DOWNLINK": true, "JOIN": true}
	for _, pt := range packetTypes {
		if !validTypes[pt] {
			return fmt.Errorf("invalid packet type: %s", pt)
		}
	}

	now := time.Now().Unix()
	policy := Policy{
		PolicyID:    policyID,
		OwnerOrg:    ownerOrg,
		Devices:     devices,
		PacketTypes: packetTypes,
		Pricing: PricingTier{
			UplinkMicro:   uplinkMicro,
			DownlinkMicro: downlinkMicro,
			JoinMicro:     joinMicro,
		},
		ValidFrom:  now,
		ValidUntil: validUntil,
		Active:     true,
		CreatedAt:  now,
	}

	policyJSON, err := json.Marshal(policy)
	if err != nil {
		return fmt.Errorf("failed to marshal policy: %v", err)
	}

	// Store the policy
	if err := ctx.GetStub().PutState(policyKey(policyID), policyJSON); err != nil {
		return fmt.Errorf("failed to store policy: %v", err)
	}

	// Create composite keys for device lookups
	for _, devEUI := range devices {
		indexKey, err := ctx.GetStub().CreateCompositeKey("device~policy", []string{strings.ToLower(devEUI), policyID})
		if err != nil {
			return fmt.Errorf("failed to create device index: %v", err)
		}
		if err := ctx.GetStub().PutState(indexKey, []byte{0x00}); err != nil {
			return fmt.Errorf("failed to store device index: %v", err)
		}
	}

	// Create org index
	orgIndexKey, err := ctx.GetStub().CreateCompositeKey("org~policy", []string{ownerOrg, policyID})
	if err != nil {
		return fmt.Errorf("failed to create org index: %v", err)
	}
	if err := ctx.GetStub().PutState(orgIndexKey, []byte{0x00}); err != nil {
		return fmt.Errorf("failed to store org index: %v", err)
	}

	return nil
}

// RecordCharge records a charge for roaming traffic
func (c *BillingContract) RecordCharge(
	ctx contractapi.TransactionContextInterface,
	devEUI string,
	gatewayEUI string,
	gatewayOwnerOrg string,
	packetType string,
	packetCount int,
) error {
	now := time.Now().Unix()
	devEUI = strings.ToLower(devEUI)

	// Find applicable policy for this device
	policy, err := c.findPolicyForDevice(ctx, devEUI)
	if err != nil {
		return fmt.Errorf("no active policy for device %s: %v", devEUI, err)
	}

	// Skip if device org == gateway org (not roaming)
	if policy.OwnerOrg == gatewayOwnerOrg {
		return nil // Not roaming, no charge needed
	}

	// Validate packet type is covered by policy
	typeAllowed := false
	for _, pt := range policy.PacketTypes {
		if pt == packetType {
			typeAllowed = true
			break
		}
	}
	if !typeAllowed {
		return fmt.Errorf("packet type %s not covered by policy %s", packetType, policy.PolicyID)
	}

	// Calculate charge amount
	var amountMicro int64
	switch packetType {
	case "UPLINK":
		amountMicro = policy.Pricing.UplinkMicro * int64(packetCount)
	case "DOWNLINK":
		amountMicro = policy.Pricing.DownlinkMicro * int64(packetCount)
	case "JOIN":
		amountMicro = policy.Pricing.JoinMicro * int64(packetCount)
	default:
		return fmt.Errorf("unknown packet type: %s", packetType)
	}

	// Create charge item
	chargeID := fmt.Sprintf("CHG_%s_%d", ctx.GetStub().GetTxID()[:8], now)
	charge := ChargeItem{
		ChargeID:    chargeID,
		PolicyID:    policy.PolicyID,
		DevEUI:      devEUI,
		GatewayEUI:  gatewayEUI,
		PacketType:  packetType,
		PacketCount: packetCount,
		AmountMicro: amountMicro,
		Timestamp:   now,
	}

	// Get or create accumulator for this org pair
	accumulator, err := c.getOrCreateAccumulator(ctx, policy.OwnerOrg, gatewayOwnerOrg)
	if err != nil {
		return err
	}

	// Add charge to accumulator
	accumulator.Charges = append(accumulator.Charges, charge)
	accumulator.TotalMicro += amountMicro
	accumulator.LastUpdated = now

	// Save accumulator
	if err := c.saveAccumulator(ctx, accumulator); err != nil {
		return err
	}

	// Emit charge event
	eventPayload := map[string]interface{}{
		"chargeID":    chargeID,
		"debtorOrg":   policy.OwnerOrg,
		"creditorOrg": gatewayOwnerOrg,
		"amountMicro": amountMicro,
	}
	eventJSON, _ := json.Marshal(eventPayload)
	ctx.GetStub().SetEvent("ChargeRecorded", eventJSON)

	return nil
}

// GetPendingCharges returns the accumulated charges between two organizations
func (c *BillingContract) GetPendingCharges(
	ctx contractapi.TransactionContextInterface,
	debtorOrg string,
	creditorOrg string,
) (*ChargeAccumulator, error) {
	accumulatorID := accumulatorKey(debtorOrg, creditorOrg)
	accumulatorJSON, err := ctx.GetStub().GetState(accumulatorID)
	if err != nil {
		return nil, fmt.Errorf("failed to read accumulator: %v", err)
	}
	if accumulatorJSON == nil {
		return nil, fmt.Errorf("no pending charges between %s and %s", debtorOrg, creditorOrg)
	}

	var accumulator ChargeAccumulator
	if err := json.Unmarshal(accumulatorJSON, &accumulator); err != nil {
		return nil, fmt.Errorf("failed to unmarshal accumulator: %v", err)
	}

	return &accumulator, nil
}

// GetAllPendingChargesForOrg returns all pending charges where the org is debtor or creditor
func (c *BillingContract) GetAllPendingChargesForOrg(
	ctx contractapi.TransactionContextInterface,
	orgID string,
) (map[string]*ChargeAccumulator, error) {
	result := make(map[string]*ChargeAccumulator)

	// Query as debtor
	debtorIterator, err := ctx.GetStub().GetStateByPartialCompositeKey("debtor~creditor", []string{orgID})
	if err == nil {
		defer debtorIterator.Close()
		for debtorIterator.HasNext() {
			kv, err := debtorIterator.Next()
			if err != nil {
				continue
			}
			_, parts, err := ctx.GetStub().SplitCompositeKey(kv.Key)
			if err != nil || len(parts) < 2 {
				continue
			}
			creditorOrg := parts[1]
			acc, err := c.GetPendingCharges(ctx, orgID, creditorOrg)
			if err == nil {
				result[fmt.Sprintf("owes_%s", creditorOrg)] = acc
			}
		}
	}

	// Query as creditor
	creditorIterator, err := ctx.GetStub().GetStateByPartialCompositeKey("creditor~debtor", []string{orgID})
	if err == nil {
		defer creditorIterator.Close()
		for creditorIterator.HasNext() {
			kv, err := creditorIterator.Next()
			if err != nil {
				continue
			}
			_, parts, err := ctx.GetStub().SplitCompositeKey(kv.Key)
			if err != nil || len(parts) < 2 {
				continue
			}
			debtorOrg := parts[1]
			acc, err := c.GetPendingCharges(ctx, debtorOrg, orgID)
			if err == nil {
				result[fmt.Sprintf("owed_by_%s", debtorOrg)] = acc
			}
		}
	}

	return result, nil
}

// InitiateSettlement creates a settlement proposal for pending charges
func (c *BillingContract) InitiateSettlement(
	ctx contractapi.TransactionContextInterface,
	debtorOrg string,
	creditorOrg string,
) (*Settlement, error) {
	// Verify caller is either debtor or creditor
	callerOrg, err := c.getCallerOrg(ctx)
	if err != nil {
		return nil, err
	}
	if callerOrg != debtorOrg && callerOrg != creditorOrg {
		return nil, fmt.Errorf("only debtor or creditor can initiate settlement")
	}

	// Get pending charges
	accumulator, err := c.GetPendingCharges(ctx, debtorOrg, creditorOrg)
	if err != nil {
		return nil, err
	}

	if accumulator.TotalMicro == 0 {
		return nil, fmt.Errorf("no pending charges to settle")
	}

	now := time.Now().Unix()
	settlementID := fmt.Sprintf("SET_%s_%s_%d", debtorOrg, creditorOrg, now)

	settlement := Settlement{
		SettlementID: settlementID,
		DebtorOrg:    debtorOrg,
		CreditorOrg:  creditorOrg,
		TotalMicro:   accumulator.TotalMicro,
		ChargeCount:  len(accumulator.Charges),
		PeriodStart:  accumulator.PeriodStart,
		PeriodEnd:    now,
		Status:       "PENDING",
		CreatedAt:    now,
	}

	settlementJSON, err := json.Marshal(settlement)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal settlement: %v", err)
	}

	// Store settlement
	if err := ctx.GetStub().PutState(settlementKey(settlementID), settlementJSON); err != nil {
		return nil, fmt.Errorf("failed to store settlement: %v", err)
	}

	// Create indices for settlement queries
	for _, prefix := range []string{"debtor~settlement", "creditor~settlement"} {
		org := debtorOrg
		if prefix == "creditor~settlement" {
			org = creditorOrg
		}
		indexKey, err := ctx.GetStub().CreateCompositeKey(prefix, []string{org, settlementID})
		if err == nil {
			ctx.GetStub().PutState(indexKey, []byte{0x00})
		}
	}

	// Archive charges (move from accumulator to settlement record)
	chargesJSON, _ := json.Marshal(accumulator.Charges)
	ctx.GetStub().PutState(fmt.Sprintf("SETTLEMENT_CHARGES_%s", settlementID), chargesJSON)

	// Reset accumulator
	accumulator.Charges = []ChargeItem{}
	accumulator.TotalMicro = 0
	accumulator.PeriodStart = now
	if err := c.saveAccumulator(ctx, accumulator); err != nil {
		return nil, err
	}

	// Emit event
	eventPayload := map[string]interface{}{
		"settlementID": settlementID,
		"debtorOrg":    debtorOrg,
		"creditorOrg":  creditorOrg,
		"totalMicro":   settlement.TotalMicro,
	}
	eventJSON, _ := json.Marshal(eventPayload)
	ctx.GetStub().SetEvent("SettlementInitiated", eventJSON)

	return &settlement, nil
}

// ConfirmPayment marks a settlement as paid
func (c *BillingContract) ConfirmPayment(
	ctx contractapi.TransactionContextInterface,
	settlementID string,
	paymentRef string,
) error {
	settlement, err := c.getSettlement(ctx, settlementID)
	if err != nil {
		return err
	}

	if settlement.Status != "PENDING" {
		return fmt.Errorf("settlement %s is not pending (status: %s)", settlementID, settlement.Status)
	}

	// Verify caller is the creditor (only they can confirm receipt)
	callerOrg, err := c.getCallerOrg(ctx)
	if err != nil {
		return err
	}
	if callerOrg != settlement.CreditorOrg {
		return fmt.Errorf("only creditor can confirm payment")
	}

	now := time.Now().Unix()
	settlement.Status = "PAID"
	settlement.PaymentRef = paymentRef
	settlement.ResolvedAt = now

	settlementJSON, err := json.Marshal(settlement)
	if err != nil {
		return fmt.Errorf("failed to marshal settlement: %v", err)
	}

	if err := ctx.GetStub().PutState(settlementKey(settlementID), settlementJSON); err != nil {
		return fmt.Errorf("failed to update settlement: %v", err)
	}

	// Emit event
	eventPayload := map[string]interface{}{
		"settlementID": settlementID,
		"status":       "PAID",
		"paymentRef":   paymentRef,
	}
	eventJSON, _ := json.Marshal(eventPayload)
	ctx.GetStub().SetEvent("SettlementConfirmed", eventJSON)

	return nil
}

// DisputeSettlement marks a settlement as disputed
func (c *BillingContract) DisputeSettlement(
	ctx contractapi.TransactionContextInterface,
	settlementID string,
	reason string,
) error {
	settlement, err := c.getSettlement(ctx, settlementID)
	if err != nil {
		return err
	}

	if settlement.Status != "PENDING" {
		return fmt.Errorf("settlement %s is not pending (status: %s)", settlementID, settlement.Status)
	}

	// Verify caller is debtor or creditor
	callerOrg, err := c.getCallerOrg(ctx)
	if err != nil {
		return err
	}
	if callerOrg != settlement.DebtorOrg && callerOrg != settlement.CreditorOrg {
		return fmt.Errorf("only debtor or creditor can dispute settlement")
	}

	settlement.Status = "DISPUTED"
	settlement.DisputeReason = reason
	settlement.ResolvedAt = time.Now().Unix()

	settlementJSON, err := json.Marshal(settlement)
	if err != nil {
		return fmt.Errorf("failed to marshal settlement: %v", err)
	}

	if err := ctx.GetStub().PutState(settlementKey(settlementID), settlementJSON); err != nil {
		return fmt.Errorf("failed to update settlement: %v", err)
	}

	return nil
}

// GetSettlement retrieves a settlement by ID
func (c *BillingContract) GetSettlement(
	ctx contractapi.TransactionContextInterface,
	settlementID string,
) (*Settlement, error) {
	return c.getSettlement(ctx, settlementID)
}

// GetSettlementsByOrg returns all settlements for an organization
func (c *BillingContract) GetSettlementsByOrg(
	ctx contractapi.TransactionContextInterface,
	orgID string,
	role string, // "debtor", "creditor", or "any"
) ([]*Settlement, error) {
	var settlements []*Settlement

	prefixes := []string{}
	switch role {
	case "debtor":
		prefixes = []string{"debtor~settlement"}
	case "creditor":
		prefixes = []string{"creditor~settlement"}
	default:
		prefixes = []string{"debtor~settlement", "creditor~settlement"}
	}

	seen := make(map[string]bool)

	for _, prefix := range prefixes {
		iterator, err := ctx.GetStub().GetStateByPartialCompositeKey(prefix, []string{orgID})
		if err != nil {
			continue
		}

		for iterator.HasNext() {
			kv, err := iterator.Next()
			if err != nil {
				continue
			}

			_, parts, err := ctx.GetStub().SplitCompositeKey(kv.Key)
			if err != nil || len(parts) < 2 {
				continue
			}

			settlementID := parts[1]
			if seen[settlementID] {
				continue
			}
			seen[settlementID] = true

			settlement, err := c.getSettlement(ctx, settlementID)
			if err == nil {
				settlements = append(settlements, settlement)
			}
		}
		iterator.Close()
	}

	// Sort by created date descending
	sort.Slice(settlements, func(i, j int) bool {
		return settlements[i].CreatedAt > settlements[j].CreatedAt
	})

	return settlements, nil
}

// GetPolicy retrieves a policy by ID
func (c *BillingContract) GetPolicy(
	ctx contractapi.TransactionContextInterface,
	policyID string,
) (*Policy, error) {
	policyJSON, err := ctx.GetStub().GetState(policyKey(policyID))
	if err != nil {
		return nil, fmt.Errorf("failed to read policy: %v", err)
	}
	if policyJSON == nil {
		return nil, fmt.Errorf("policy %s does not exist", policyID)
	}

	var policy Policy
	if err := json.Unmarshal(policyJSON, &policy); err != nil {
		return nil, fmt.Errorf("failed to unmarshal policy: %v", err)
	}

	return &policy, nil
}

// DeactivatePolicy deactivates a policy
func (c *BillingContract) DeactivatePolicy(
	ctx contractapi.TransactionContextInterface,
	policyID string,
) error {
	policy, err := c.GetPolicy(ctx, policyID)
	if err != nil {
		return err
	}

	// Verify caller owns the policy
	callerOrg, err := c.getCallerOrg(ctx)
	if err != nil {
		return err
	}
	if callerOrg != policy.OwnerOrg {
		return fmt.Errorf("only policy owner can deactivate")
	}

	policy.Active = false

	policyJSON, err := json.Marshal(policy)
	if err != nil {
		return fmt.Errorf("failed to marshal policy: %v", err)
	}

	return ctx.GetStub().PutState(policyKey(policyID), policyJSON)
}

// Helper functions

func policyKey(policyID string) string {
	return fmt.Sprintf("POLICY_%s", policyID)
}

func accumulatorKey(debtorOrg, creditorOrg string) string {
	return fmt.Sprintf("ACC_%s_%s", debtorOrg, creditorOrg)
}

func settlementKey(settlementID string) string {
	return fmt.Sprintf("SETTLEMENT_%s", settlementID)
}

func (c *BillingContract) getCallerOrg(ctx contractapi.TransactionContextInterface) (string, error) {
	mspID, err := ctx.GetClientIdentity().GetMSPID()
	if err != nil {
		return "", fmt.Errorf("failed to get client MSPID: %v", err)
	}
	// Remove "MSP" suffix if present
	org := mspID
	if len(mspID) > 3 && mspID[len(mspID)-3:] == "MSP" {
		org = mspID[:len(mspID)-3]
	}
	return org, nil
}

func (c *BillingContract) findPolicyForDevice(
	ctx contractapi.TransactionContextInterface,
	devEUI string,
) (*Policy, error) {
	now := time.Now().Unix()

	iterator, err := ctx.GetStub().GetStateByPartialCompositeKey("device~policy", []string{devEUI})
	if err != nil {
		return nil, fmt.Errorf("failed to query device policies: %v", err)
	}
	defer iterator.Close()

	for iterator.HasNext() {
		kv, err := iterator.Next()
		if err != nil {
			continue
		}

		_, parts, err := ctx.GetStub().SplitCompositeKey(kv.Key)
		if err != nil || len(parts) < 2 {
			continue
		}

		policyID := parts[1]
		policy, err := c.GetPolicy(ctx, policyID)
		if err != nil {
			continue
		}

		// Check if policy is active and valid
		if policy.Active && policy.ValidFrom <= now && policy.ValidUntil > now {
			return policy, nil
		}
	}

	return nil, fmt.Errorf("no active policy found for device %s", devEUI)
}

func (c *BillingContract) getOrCreateAccumulator(
	ctx contractapi.TransactionContextInterface,
	debtorOrg string,
	creditorOrg string,
) (*ChargeAccumulator, error) {
	accID := accumulatorKey(debtorOrg, creditorOrg)
	accJSON, err := ctx.GetStub().GetState(accID)
	if err != nil {
		return nil, fmt.Errorf("failed to read accumulator: %v", err)
	}

	if accJSON != nil {
		var accumulator ChargeAccumulator
		if err := json.Unmarshal(accJSON, &accumulator); err != nil {
			return nil, fmt.Errorf("failed to unmarshal accumulator: %v", err)
		}
		return &accumulator, nil
	}

	// Create new accumulator
	now := time.Now().Unix()
	accumulator := ChargeAccumulator{
		AccumulatorID: accID,
		DebtorOrg:     debtorOrg,
		CreditorOrg:   creditorOrg,
		TotalMicro:    0,
		Charges:       []ChargeItem{},
		PeriodStart:   now,
		LastUpdated:   now,
	}

	// Create indices for org queries
	debtorKey, _ := ctx.GetStub().CreateCompositeKey("debtor~creditor", []string{debtorOrg, creditorOrg})
	ctx.GetStub().PutState(debtorKey, []byte{0x00})

	creditorKey, _ := ctx.GetStub().CreateCompositeKey("creditor~debtor", []string{creditorOrg, debtorOrg})
	ctx.GetStub().PutState(creditorKey, []byte{0x00})

	return &accumulator, nil
}

func (c *BillingContract) saveAccumulator(
	ctx contractapi.TransactionContextInterface,
	accumulator *ChargeAccumulator,
) error {
	accJSON, err := json.Marshal(accumulator)
	if err != nil {
		return fmt.Errorf("failed to marshal accumulator: %v", err)
	}

	return ctx.GetStub().PutState(accumulator.AccumulatorID, accJSON)
}

func (c *BillingContract) getSettlement(
	ctx contractapi.TransactionContextInterface,
	settlementID string,
) (*Settlement, error) {
	settlementJSON, err := ctx.GetStub().GetState(settlementKey(settlementID))
	if err != nil {
		return nil, fmt.Errorf("failed to read settlement: %v", err)
	}
	if settlementJSON == nil {
		return nil, fmt.Errorf("settlement %s does not exist", settlementID)
	}

	var settlement Settlement
	if err := json.Unmarshal(settlementJSON, &settlement); err != nil {
		return nil, fmt.Errorf("failed to unmarshal settlement: %v", err)
	}

	return &settlement, nil
}

func main() {
	chaincode, err := contractapi.NewChaincode(&BillingContract{})
	if err != nil {
		fmt.Printf("Error creating Billing chaincode: %v\n", err)
		return
	}

	if err := chaincode.Start(); err != nil {
		fmt.Printf("Error starting Billing chaincode: %v\n", err)
	}
}
