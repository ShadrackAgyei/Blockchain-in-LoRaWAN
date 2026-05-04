#!/usr/bin/env python3
"""
Analysis script for physical LoRaWAN testbed data.

Reads data from MySQL (webhook_events, billing_charges) and Hyperledger Fabric
(forwarding history, trust scores) to produce publication-quality figures
that complement the simulation analysis.

Usage:
  python scripts/analyze_physical.py [--db-port 3307] [--output-dir results/physical]
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd
import pymysql


# ── Configuration ──

PHYSICAL_GW_EUI = "2CCF67FFFE6491D1"
PHYSICAL_DEV_EUI = "70B3D57ED0075A44"
SESSION_START = "2026-03-30 21:00:00"  # When physical testbed started

# Simulation reference values (reliable profile from simulate.py)
SIM_REFERENCE = {
    "trust_score": 0.911,
    "avg_rssi": -71.67,
    "avg_snr": 8.33,
    "reliability": 0.987,
    "error_rate": 0.013,
}

COLORS = {
    "primary": "#1565C0",
    "secondary": "#00B8D4",
    "accent": "#0B1D3A",
    "physical": "#2ecc71",
    "simulation": "#3498db",
    "rssi": "#e74c3c",
    "snr": "#2ecc71",
    "billing": "#f39c12",
}


# ── Data Loading ──

def load_mysql_events(host="127.0.0.1", port=3307, user="lorawan",
                      password="lorawan", db="lorawan_events") -> pd.DataFrame:
    """Load webhook events from MySQL for the physical testbed session."""
    conn = pymysql.connect(host=host, port=port, user=user,
                           password=password, database=db)
    query = f"""
        SELECT id, event_type, dev_eui, gateway_eui, rssi, snr,
               timestamp, processed, blockchain_tx_id, created_at
        FROM webhook_events
        WHERE dev_eui = '{PHYSICAL_DEV_EUI}'
          AND gateway_eui = '{PHYSICAL_GW_EUI}'
          AND timestamp >= '{SESSION_START}'
        ORDER BY timestamp ASC
    """
    df = pd.read_sql(query, conn)
    conn.close()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    print(f"  Loaded {len(df)} physical events from MySQL")
    return df


def load_mysql_billing(host="127.0.0.1", port=3307, user="lorawan",
                       password="lorawan", db="lorawan_events") -> pd.DataFrame:
    """Load billing charges from MySQL."""
    conn = pymysql.connect(host=host, port=port, user=user,
                           password=password, database=db)
    query = f"""
        SELECT * FROM billing_charges
        WHERE created_at >= '{SESSION_START}'
        ORDER BY created_at ASC
    """
    try:
        df = pd.read_sql(query, conn)
        df["created_at"] = pd.to_datetime(df["created_at"])
        print(f"  Loaded {len(df)} billing charges from MySQL")
    except Exception as e:
        print(f"  WARNING: Could not load billing_charges: {e}")
        df = pd.DataFrame()
    conn.close()
    return df


def load_blockchain_forwarding() -> list:
    """Load forwarding history from Hyperledger Fabric."""
    env = _fabric_env()
    cmd = [
        "peer", "chaincode", "query",
        "-C", "lorawan-channel", "-n", "trustmanagement",
        "-c", json.dumps({
            "function": "GetForwardingHistory",
            "Args": [PHYSICAL_GW_EUI, "0", "9999999999"]
        })
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        print(f"  WARNING: Fabric query failed: {result.stderr.strip()}")
        return []
    records = json.loads(result.stdout)
    print(f"  Loaded {len(records)} forwarding batches from blockchain")
    return records


def load_blockchain_trust_score() -> float:
    """Get current trust score from blockchain."""
    env = _fabric_env()
    cmd = [
        "peer", "chaincode", "query",
        "-C", "lorawan-channel", "-n", "trustmanagement",
        "-c", json.dumps({
            "function": "GetGateway",
            "Args": [PHYSICAL_GW_EUI]
        })
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        print(f"  WARNING: Trust score query failed: {result.stderr.strip()}")
        return 0.0
    gw = json.loads(result.stdout)
    score = gw.get("trustScore", 0.0)
    print(f"  Current trust score: {score}")
    return score


def _fabric_env() -> dict:
    """Build environment for Fabric peer CLI commands."""
    home = os.path.expanduser("~")
    fabric_path = os.path.join(home, "fabric-samples")
    env = os.environ.copy()
    env["PATH"] = os.path.join(fabric_path, "bin") + ":" + env.get("PATH", "")
    env["FABRIC_CFG_PATH"] = os.path.join(fabric_path, "config")
    env["CORE_PEER_TLS_ENABLED"] = "true"
    env["CORE_PEER_LOCALMSPID"] = "Org1MSP"
    env["CORE_PEER_TLS_ROOTCERT_FILE"] = os.path.join(
        fabric_path, "test-network/organizations/peerOrganizations/"
        "org1.example.com/peers/peer0.org1.example.com/tls/ca.crt")
    env["CORE_PEER_MSPCONFIGPATH"] = os.path.join(
        fabric_path, "test-network/organizations/peerOrganizations/"
        "org1.example.com/users/Admin@org1.example.com/msp")
    env["CORE_PEER_ADDRESS"] = "localhost:7051"
    return env


# ── Figures ──

def fig1_signal_quality(df: pd.DataFrame, out_dir: str):
    """Figure 1: RSSI and SNR over time from physical testbed."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
    fig.suptitle("Physical Testbed: Signal Quality Over Time",
                 fontsize=16, fontweight="bold", y=0.95)

    # RSSI
    ax1.scatter(df["timestamp"], df["rssi"], c=COLORS["rssi"],
                alpha=0.4, s=8, edgecolors="none")
    # Rolling average (window=20)
    if len(df) >= 20:
        rolling_rssi = df["rssi"].rolling(window=20, center=True).mean()
        ax1.plot(df["timestamp"], rolling_rssi, color=COLORS["accent"],
                 linewidth=2, label="20-sample rolling avg")
    ax1.set_ylabel("RSSI (dBm)", fontsize=12)
    ax1.axhline(y=df["rssi"].mean(), color=COLORS["rssi"], linestyle="--",
                alpha=0.5, label=f'Mean: {df["rssi"].mean():.1f} dBm')
    ax1.legend(fontsize=10)
    ax1.grid(True, alpha=0.3)

    # SNR
    ax2.scatter(df["timestamp"], df["snr"], c=COLORS["snr"],
                alpha=0.4, s=8, edgecolors="none")
    if len(df) >= 20:
        rolling_snr = df["snr"].rolling(window=20, center=True).mean()
        ax2.plot(df["timestamp"], rolling_snr, color=COLORS["accent"],
                 linewidth=2, label="20-sample rolling avg")
    ax2.set_ylabel("SNR (dB)", fontsize=12)
    ax2.set_xlabel("Time", fontsize=12)
    ax2.axhline(y=df["snr"].mean(), color=COLORS["snr"], linestyle="--",
                alpha=0.5, label=f'Mean: {df["snr"].mean():.1f} dB')
    ax2.legend(fontsize=10)
    ax2.grid(True, alpha=0.3)

    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax2.xaxis.set_major_locator(mdates.HourLocator(interval=2))
    fig.autofmt_xdate()

    plt.tight_layout()
    path = os.path.join(out_dir, "phys_fig1_signal_quality.png")
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {path}")


def fig2_trust_convergence(forwarding_records: list, out_dir: str):
    """Figure 2: Trust score convergence computed from forwarding batches."""
    if not forwarding_records:
        print("  Skipping trust convergence: no forwarding records")
        return

    # Compute cumulative trust score at each batch
    scores = []
    cum_reliability_num = 0.0
    cum_reliability_den = 0.0
    cum_signal_num = 0.0
    cum_signal_den = 0.0

    for i, rec in enumerate(forwarding_records):
        total = rec["uplinkCount"] + rec["downlinkCount"] + rec["joinCount"]
        errors = rec["errorCount"]
        if total > 0:
            cum_reliability_num += (total - errors)
            cum_reliability_den += total
            # Normalize RSSI [-120, -40] -> [0, 1]
            rssi_norm = max(0, min(1, (rec["avgRSSI"] + 120) / 80))
            # Normalize SNR [-20, 10] -> [0, 1]
            snr_norm = max(0, min(1, (rec["avgSNR"] + 20) / 30))
            signal = (rssi_norm + snr_norm) / 2
            cum_signal_num += signal * total
            cum_signal_den += total

        if cum_reliability_den > 0:
            R = cum_reliability_num / cum_reliability_den
            Q = cum_signal_num / cum_signal_den if cum_signal_den > 0 else 0
            T = 0.6 * R + 0.4 * Q
            scores.append(T)
        else:
            scores.append(0.5)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(range(1, len(scores) + 1), scores, color=COLORS["primary"],
            linewidth=2, label="Physical gateway trust score")
    ax.axhline(y=0.7, color="#e74c3c", linestyle="--", alpha=0.7,
               label="Trust threshold (0.7)")
    ax.axhline(y=SIM_REFERENCE["trust_score"], color=COLORS["simulation"],
               linestyle=":", alpha=0.7,
               label=f'Simulation reliable ({SIM_REFERENCE["trust_score"]})')

    ax.set_xlabel("Forwarding Batch Number", fontsize=12)
    ax.set_ylabel("Trust Score", fontsize=12)
    ax.set_title("Physical Testbed: Trust Score Convergence",
                 fontsize=14, fontweight="bold")
    ax.set_ylim(0.4, 1.05)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)

    # Annotate final score
    if scores:
        ax.annotate(f"Final: {scores[-1]:.3f}",
                    xy=(len(scores), scores[-1]),
                    xytext=(-80, -30), textcoords="offset points",
                    fontsize=11, fontweight="bold",
                    arrowprops=dict(arrowstyle="->", color=COLORS["accent"]),
                    color=COLORS["accent"])

    plt.tight_layout()
    path = os.path.join(out_dir, "phys_fig2_trust_convergence.png")
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {path}")

    return scores


def fig3_billing_accumulation(df_events: pd.DataFrame, out_dir: str):
    """Figure 3: Cumulative billing charges over time."""
    # Each uplink from Org2 device through Org1 gateway = 100 micro-cents
    df = df_events.copy()
    df["charge_micro"] = 100  # uplink rate
    df["cumulative_micro"] = df["charge_micro"].cumsum()
    df["cumulative_cents"] = df["cumulative_micro"] / 10000  # to dollars

    fig, ax1 = plt.subplots(figsize=(10, 5))

    ax1.fill_between(df["timestamp"], df["cumulative_micro"] / 1000,
                     alpha=0.3, color=COLORS["billing"])
    ax1.plot(df["timestamp"], df["cumulative_micro"] / 1000,
             color=COLORS["billing"], linewidth=2, label="Cumulative charges")

    ax1.set_xlabel("Time", fontsize=12)
    ax1.set_ylabel("Charges (milli-cents)", fontsize=12)
    ax1.set_title("Physical Testbed: Roaming Billing Accumulation (Org2 → Org1)",
                  fontsize=14, fontweight="bold")
    ax1.grid(True, alpha=0.3)

    # Annotate total
    total_micro = len(df) * 100
    ax1.annotate(f"Total: {total_micro:,} micro-cents\n({len(df)} roaming packets)",
                 xy=(df["timestamp"].iloc[-1], df["cumulative_micro"].iloc[-1] / 1000),
                 xytext=(-180, -40), textcoords="offset points",
                 fontsize=11, fontweight="bold",
                 arrowprops=dict(arrowstyle="->", color=COLORS["accent"]),
                 color=COLORS["accent"])

    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax1.xaxis.set_major_locator(mdates.HourLocator(interval=3))
    fig.autofmt_xdate()

    plt.tight_layout()
    path = os.path.join(out_dir, "phys_fig3_billing_accumulation.png")
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {path}")


def fig4_comparison(df_events: pd.DataFrame, trust_score: float,
                    forwarding_records: list, out_dir: str):
    """Figure 4: Physical testbed vs simulation comparison."""
    # Compute physical metrics
    phys_reliability = 1.0  # 0 errors in forwarding records
    if forwarding_records:
        total_packets = sum(r["uplinkCount"] + r["downlinkCount"] + r["joinCount"]
                          for r in forwarding_records)
        total_errors = sum(r["errorCount"] for r in forwarding_records)
        if total_packets > 0:
            phys_reliability = (total_packets - total_errors) / total_packets

    phys_metrics = {
        "Trust Score": trust_score,
        "Reliability": phys_reliability,
        "Avg RSSI\n(normalized)": max(0, min(1, (df_events["rssi"].mean() + 120) / 80)),
        "Avg SNR\n(normalized)": max(0, min(1, (df_events["snr"].mean() + 20) / 30)),
    }

    sim_metrics = {
        "Trust Score": SIM_REFERENCE["trust_score"],
        "Reliability": SIM_REFERENCE["reliability"],
        "Avg RSSI\n(normalized)": max(0, min(1, (SIM_REFERENCE["avg_rssi"] + 120) / 80)),
        "Avg SNR\n(normalized)": max(0, min(1, (SIM_REFERENCE["avg_snr"] + 20) / 30)),
    }

    labels = list(phys_metrics.keys())
    phys_vals = list(phys_metrics.values())
    sim_vals = list(sim_metrics.values())

    x = np.arange(len(labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 5))
    bars1 = ax.bar(x - width/2, phys_vals, width, label="Physical Testbed",
                   color=COLORS["physical"], alpha=0.85, edgecolor="white")
    bars2 = ax.bar(x + width/2, sim_vals, width, label="Simulation (Reliable)",
                   color=COLORS["simulation"], alpha=0.85, edgecolor="white")

    # Value labels on bars
    for bars in [bars1, bars2]:
        for bar in bars:
            height = bar.get_height()
            ax.annotate(f"{height:.3f}",
                       xy=(bar.get_x() + bar.get_width() / 2, height),
                       xytext=(0, 4), textcoords="offset points",
                       ha="center", va="bottom", fontsize=10, fontweight="bold")

    ax.set_ylabel("Score (0-1)", fontsize=12)
    ax.set_title("Physical Testbed vs Simulation: Key Metrics Comparison",
                 fontsize=14, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_ylim(0, 1.15)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    path = os.path.join(out_dir, "phys_fig4_comparison.png")
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {path}")


def fig5_event_throughput(df: pd.DataFrame, out_dir: str):
    """Figure 5: Events per hour over the testbed session."""
    df = df.copy()
    df["hour"] = df["timestamp"].dt.floor("h")
    hourly = df.groupby("hour").size().reset_index(name="count")

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(hourly["hour"], hourly["count"], width=timedelta(hours=0.8),
           color=COLORS["primary"], alpha=0.8, edgecolor="white")

    avg_rate = hourly["count"].mean()
    ax.axhline(y=avg_rate, color=COLORS["secondary"], linestyle="--",
               linewidth=2, label=f"Avg: {avg_rate:.0f} events/hr")

    ax.set_xlabel("Time", fontsize=12)
    ax.set_ylabel("Events per Hour", fontsize=12)
    ax.set_title("Physical Testbed: Event Throughput",
                 fontsize=14, fontweight="bold")
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3, axis="y")

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=3))
    fig.autofmt_xdate()

    plt.tight_layout()
    path = os.path.join(out_dir, "phys_fig5_event_throughput.png")
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {path}")


# ── Summary ──

def generate_summary(df_events: pd.DataFrame, trust_score: float,
                     forwarding_records: list) -> dict:
    """Generate summary statistics JSON."""
    total_batches = len(forwarding_records)
    total_uplinks = sum(r["uplinkCount"] for r in forwarding_records) if forwarding_records else 0
    total_errors = sum(r["errorCount"] for r in forwarding_records) if forwarding_records else 0

    duration_hours = 0
    if len(df_events) > 1:
        duration = df_events["timestamp"].max() - df_events["timestamp"].min()
        duration_hours = duration.total_seconds() / 3600

    summary = {
        "testbed": {
            "device_eui": PHYSICAL_DEV_EUI,
            "gateway_eui": PHYSICAL_GW_EUI,
            "duration_hours": round(duration_hours, 1),
            "start_time": str(df_events["timestamp"].min()) if len(df_events) > 0 else None,
            "end_time": str(df_events["timestamp"].max()) if len(df_events) > 0 else None,
        },
        "events": {
            "total_webhook_events": len(df_events),
            "events_per_hour": round(len(df_events) / max(duration_hours, 1), 1),
        },
        "signal_quality": {
            "rssi_mean": round(df_events["rssi"].mean(), 2),
            "rssi_std": round(df_events["rssi"].std(), 2),
            "rssi_min": float(df_events["rssi"].min()),
            "rssi_max": float(df_events["rssi"].max()),
            "snr_mean": round(df_events["snr"].mean(), 2),
            "snr_std": round(df_events["snr"].std(), 2),
            "snr_min": float(df_events["snr"].min()),
            "snr_max": float(df_events["snr"].max()),
        },
        "blockchain": {
            "forwarding_batches": total_batches,
            "total_uplinks_on_chain": total_uplinks,
            "total_errors": total_errors,
            "reliability": round((total_uplinks - total_errors) / max(total_uplinks, 1), 4),
            "trust_score": trust_score,
        },
        "billing": {
            "roaming_packets": len(df_events),
            "total_micro_cents": len(df_events) * 100,
            "debtor_org": "Org2",
            "creditor_org": "Org1",
        },
        "comparison_with_simulation": {
            "physical_trust_score": trust_score,
            "simulation_reliable_trust_score": SIM_REFERENCE["trust_score"],
            "difference": round(abs(trust_score - SIM_REFERENCE["trust_score"]), 4),
            "physical_rssi_mean": round(df_events["rssi"].mean(), 2),
            "simulation_rssi_mean": SIM_REFERENCE["avg_rssi"],
            "physical_snr_mean": round(df_events["snr"].mean(), 2),
            "simulation_snr_mean": SIM_REFERENCE["avg_snr"],
        },
    }
    return summary


def print_summary(summary: dict):
    """Print formatted summary to console."""
    print("\n" + "=" * 60)
    print("  PHYSICAL TESTBED EVALUATION SUMMARY")
    print("=" * 60)

    tb = summary["testbed"]
    print(f"\n  Duration:        {tb['duration_hours']} hours")
    print(f"  Device EUI:      {tb['device_eui']}")
    print(f"  Gateway EUI:     {tb['gateway_eui']}")

    ev = summary["events"]
    print(f"\n  Total Events:    {ev['total_webhook_events']}")
    print(f"  Events/Hour:     {ev['events_per_hour']}")

    sq = summary["signal_quality"]
    print(f"\n  RSSI:            {sq['rssi_mean']:.1f} dBm "
          f"(std: {sq['rssi_std']:.1f}, range: {sq['rssi_min']:.0f} to {sq['rssi_max']:.0f})")
    print(f"  SNR:             {sq['snr_mean']:.1f} dB "
          f"(std: {sq['snr_std']:.1f}, range: {sq['snr_min']:.1f} to {sq['snr_max']:.1f})")

    bc = summary["blockchain"]
    print(f"\n  On-Chain Batches: {bc['forwarding_batches']}")
    print(f"  On-Chain Uplinks: {bc['total_uplinks_on_chain']}")
    print(f"  Reliability:      {bc['reliability']:.4f} ({bc['total_errors']} errors)")
    print(f"  Trust Score:      {bc['trust_score']:.4f}")

    bl = summary["billing"]
    print(f"\n  Roaming Packets:  {bl['roaming_packets']}")
    print(f"  Total Charges:    {bl['total_micro_cents']:,} micro-cents")
    print(f"  Direction:        {bl['debtor_org']} → {bl['creditor_org']}")

    comp = summary["comparison_with_simulation"]
    print(f"\n  ── Physical vs Simulation (Reliable Profile) ──")
    print(f"  Trust Score:     {comp['physical_trust_score']:.4f} vs "
          f"{comp['simulation_reliable_trust_score']:.4f} "
          f"(diff: {comp['difference']:.4f})")
    print(f"  RSSI:            {comp['physical_rssi_mean']:.1f} vs "
          f"{comp['simulation_rssi_mean']:.1f} dBm")
    print(f"  SNR:             {comp['physical_snr_mean']:.1f} vs "
          f"{comp['simulation_snr_mean']:.1f} dB")
    print("=" * 60)


# ── Main ──

def main():
    parser = argparse.ArgumentParser(description="Analyze physical testbed data")
    parser.add_argument("--db-port", type=int, default=3307,
                        help="MySQL port (default: 3307)")
    parser.add_argument("--output-dir", default="results/physical",
                        help="Output directory for figures and summary")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    print("=== Physical Testbed Analysis ===\n")

    # Load data
    print("Loading data...")
    df_events = load_mysql_events(port=args.db_port)
    forwarding_records = load_blockchain_forwarding()
    trust_score = load_blockchain_trust_score()

    if df_events.empty:
        print("ERROR: No physical events found. Is the testbed running?")
        sys.exit(1)

    # Generate figures
    print("\nGenerating figures...")
    fig1_signal_quality(df_events, args.output_dir)
    trust_scores = fig2_trust_convergence(forwarding_records, args.output_dir)
    fig3_billing_accumulation(df_events, args.output_dir)
    fig4_comparison(df_events, trust_score, forwarding_records, args.output_dir)
    fig5_event_throughput(df_events, args.output_dir)

    # Generate summary
    summary = generate_summary(df_events, trust_score, forwarding_records)
    summary_path = os.path.join(args.output_dir, "physical_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n  Saved summary to {summary_path}")

    print_summary(summary)
    print(f"\nAll figures saved to {args.output_dir}/")


if __name__ == "__main__":
    main()
