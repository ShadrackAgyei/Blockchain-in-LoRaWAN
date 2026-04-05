#!/usr/bin/env python3
"""
Analysis script for LoRaWAN blockchain evaluation.

Reads CSV output from simulate.py and produces 6 publication-quality
figures + a summary table for Chapter 4.

Usage:
  python scripts/analyze.py [--results-dir results]
"""

import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd


# Color scheme by profile
PROFILE_COLORS = {
    "reliable": "#2ecc71",   # green
    "average": "#f39c12",    # yellow/orange
    "poor": "#e74c3c",       # red
    "degrading": "#3498db",  # blue
}

PROFILE_ORDER = ["reliable", "average", "poor", "degrading"]


def load_data(results_dir: str) -> dict:
    """Load all CSV files into DataFrames."""
    data = {}
    for name in ["trust_scores", "latencies", "billing", "events"]:
        path = os.path.join(results_dir, f"{name}.csv")
        if os.path.exists(path):
            data[name] = pd.read_csv(path)
            print(f"  Loaded {name}: {len(data[name])} rows")
        else:
            print(f"  WARNING: {path} not found")
            data[name] = pd.DataFrame()
    return data


def fig1_trust_convergence(df: pd.DataFrame, out_dir: str):
    """Figure 1: Trust score convergence over rounds."""
    if df.empty:
        return

    fig, ax = plt.subplots(figsize=(10, 6))

    for eui in df["gateway_eui"].unique():
        gw_data = df[df["gateway_eui"] == eui].sort_values("round")
        profile = gw_data["profile"].iloc[0]
        color = PROFILE_COLORS.get(profile, "#95a5a6")
        label = gw_data["gateway_name"].iloc[0] if "gateway_name" in gw_data.columns else eui[-8:]
        linestyle = "--" if profile == "degrading" else "-"
        ax.plot(
            gw_data["round"] + 1,  # 1-indexed for display
            gw_data["trust_score"],
            color=color, linestyle=linestyle,
            marker="o", markersize=4, linewidth=1.5,
            label=f"{label} ({profile})",
        )

    ax.set_xlabel("Simulation Round", fontsize=12)
    ax.set_ylabel("Trust Score", fontsize=12)
    ax.set_title("Trust Score Convergence Over Time", fontsize=14)
    ax.set_ylim(-0.05, 1.05)
    ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax.axhline(y=0.5, color="gray", linestyle=":", alpha=0.5, label="Initial score (0.5)")
    ax.axhline(y=0.7, color="gray", linestyle="--", alpha=0.3, label="Trust threshold (0.7)")
    ax.legend(fontsize=8, loc="center left", bbox_to_anchor=(1, 0.5))
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "fig1_trust_convergence.png"), dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("  Fig 1: Trust Score Convergence — saved")


def fig2_trust_by_profile(df: pd.DataFrame, out_dir: str):
    """Figure 2: Box plot of final trust scores by profile."""
    if df.empty:
        return

    # Get final round scores
    max_round = df["round"].max()
    final = df[df["round"] == max_round]

    fig, ax = plt.subplots(figsize=(8, 6))

    box_data = []
    labels = []
    colors = []
    for profile in PROFILE_ORDER:
        scores = final[final["profile"] == profile]["trust_score"].values
        if len(scores) > 0:
            box_data.append(scores)
            labels.append(profile.capitalize())
            colors.append(PROFILE_COLORS[profile])

    bp = ax.boxplot(box_data, labels=labels, patch_artist=True, widths=0.6)
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)

    # Overlay individual points
    for i, (scores, color) in enumerate(zip(box_data, colors)):
        x = np.random.normal(i + 1, 0.04, size=len(scores))
        ax.scatter(x, scores, color=color, edgecolors="black", s=50, zorder=5)

    ax.set_ylabel("Trust Score", fontsize=12)
    ax.set_title("Final Trust Scores by Gateway Profile", fontsize=14)
    ax.set_ylim(-0.05, 1.05)
    ax.axhline(y=0.7, color="gray", linestyle="--", alpha=0.5, label="Trust threshold (0.7)")
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "fig2_trust_by_profile.png"), dpi=300)
    plt.close(fig)
    print("  Fig 2: Trust Score by Profile — saved")


def fig3_latency_distribution(df: pd.DataFrame, out_dir: str):
    """Figure 3: Transaction latency histogram + CDF."""
    if df.empty:
        return

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    # Separate invoke (write) vs query (read) operations
    invoke_ops = ["webhook_uplink", "aggregator_flush", "compute_trust"]
    query_ops = ["query_trust", "query_billing"]

    invoke_lat = df[df["operation"].isin(invoke_ops)]["latency_ms"].dropna()
    query_lat = df[df["operation"].isin(query_ops)]["latency_ms"].dropna()

    # Histogram
    if len(invoke_lat) > 0:
        ax1.hist(invoke_lat, bins=30, alpha=0.7, color="#e74c3c", label=f"Write ops (n={len(invoke_lat)})")
    if len(query_lat) > 0:
        ax1.hist(query_lat, bins=30, alpha=0.7, color="#3498db", label=f"Read ops (n={len(query_lat)})")

    ax1.set_xlabel("Latency (ms)", fontsize=12)
    ax1.set_ylabel("Count", fontsize=12)
    ax1.set_title("Transaction Latency Distribution", fontsize=14)
    ax1.legend(fontsize=10)
    ax1.grid(True, alpha=0.3)

    # CDF
    all_lat = df["latency_ms"].dropna().sort_values()
    if len(all_lat) > 0:
        cdf = np.arange(1, len(all_lat) + 1) / len(all_lat)
        ax2.plot(all_lat, cdf, color="#2c3e50", linewidth=2)

        # Annotate percentiles
        for p, label in [(50, "p50"), (95, "p95"), (99, "p99")]:
            val = np.percentile(all_lat, p)
            y = p / 100
            ax2.axhline(y=y, color="gray", linestyle=":", alpha=0.3)
            ax2.axvline(x=val, color="gray", linestyle=":", alpha=0.3)
            ax2.annotate(
                f"{label}: {val:.0f}ms",
                xy=(val, y), fontsize=9,
                xytext=(10, -5), textcoords="offset points",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="gray"),
            )

    ax2.set_xlabel("Latency (ms)", fontsize=12)
    ax2.set_ylabel("Cumulative Probability", fontsize=12)
    ax2.set_title("Latency CDF with Percentiles", fontsize=14)
    ax2.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "fig3_latency_distribution.png"), dpi=300)
    plt.close(fig)
    print("  Fig 3: Latency Distribution — saved")


def fig4_latency_over_time(df: pd.DataFrame, out_dir: str):
    """Figure 4: Latency scatter plot over time."""
    if df.empty:
        return

    fig, ax = plt.subplots(figsize=(12, 5))

    op_colors = {
        "webhook_uplink": "#e74c3c",
        "compute_trust": "#e67e22",
        "query_trust": "#3498db",
        "query_billing": "#2ecc71",
        "aggregator_flush": "#9b59b6",
    }

    for op, color in op_colors.items():
        subset = df[df["operation"] == op]
        if len(subset) > 0:
            ax.scatter(
                range(len(subset)), subset["latency_ms"],
                color=color, alpha=0.4, s=10, label=op.replace("_", " ").title(),
            )

    ax.set_xlabel("Transaction Sequence", fontsize=12)
    ax.set_ylabel("Latency (ms)", fontsize=12)
    ax.set_title("Transaction Latency Over Simulation Timeline", fontsize=14)
    ax.legend(fontsize=8, loc="upper right", markerscale=3)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "fig4_latency_over_time.png"), dpi=300)
    plt.close(fig)
    print("  Fig 4: Latency Over Time — saved")


def fig5_billing_accumulation(df: pd.DataFrame, out_dir: str):
    """Figure 5: Billing charges accumulation per round."""
    if df.empty:
        return

    fig, ax = plt.subplots(figsize=(10, 6))

    # Sum charges across org pairs per round
    round_totals = df.groupby("round")["total_micro"].sum().reset_index()
    rounds = round_totals["round"] + 1  # 1-indexed

    ax.bar(rounds, round_totals["total_micro"], color="#3498db", alpha=0.8, edgecolor="white")

    # Add cumulative line
    cumulative = round_totals["total_micro"].cumsum()
    ax2 = ax.twinx()
    ax2.plot(rounds, cumulative, color="#e74c3c", linewidth=2, marker="s", markersize=5, label="Cumulative")
    ax2.set_ylabel("Cumulative Charges (microcents)", fontsize=12, color="#e74c3c")

    ax.set_xlabel("Simulation Round", fontsize=12)
    ax.set_ylabel("Charges per Round (microcents)", fontsize=12)
    ax.set_title("Roaming Billing Charges Over Time", fontsize=14)
    ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax.grid(True, alpha=0.3, axis="y")
    ax2.legend(loc="upper left", fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "fig5_billing_accumulation.png"), dpi=300)
    plt.close(fig)
    print("  Fig 5: Billing Accumulation — saved")


def fig6_settlement_flow(df: pd.DataFrame, out_dir: str):
    """Figure 6: Settlement flow timeline visualization."""
    if df.empty:
        return

    fig, ax = plt.subplots(figsize=(10, 4))

    # Show Org2→Org1 charges over rounds
    org2_to_org1 = df[(df["debtor_org"] == "Org2") & (df["creditor_org"] == "Org1")]
    org1_to_org2 = df[(df["debtor_org"] == "Org1") & (df["creditor_org"] == "Org2")]

    if not org2_to_org1.empty:
        ax.step(
            org2_to_org1["round"] + 1, org2_to_org1["total_micro"],
            where="mid", color="#e74c3c", linewidth=2, label="Org2 owes Org1",
        )
    if not org1_to_org2.empty:
        ax.step(
            org1_to_org2["round"] + 1, org1_to_org2["total_micro"],
            where="mid", color="#3498db", linewidth=2, label="Org1 owes Org2",
        )

    # Annotate settlement point at the end
    max_round = df["round"].max() + 1
    ax.axvline(x=max_round + 0.5, color="#2ecc71", linewidth=2, linestyle="--", label="Settlement initiated")
    ax.annotate(
        "InitiateSettlement\n→ ConfirmPayment",
        xy=(max_round + 0.5, ax.get_ylim()[1] * 0.7),
        fontsize=9, ha="center",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#2ecc71", alpha=0.3),
    )

    ax.set_xlabel("Simulation Round", fontsize=12)
    ax.set_ylabel("Pending Charges (microcents)", fontsize=12)
    ax.set_title("Settlement Flow: Charge Accumulation → Settlement", fontsize=14)
    ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "fig6_settlement_flow.png"), dpi=300)
    plt.close(fig)
    print("  Fig 6: Settlement Flow — saved")


def print_summary_table(data: dict):
    """Print a summary statistics table."""
    print("\n" + "=" * 60)
    print("SUMMARY TABLE FOR CHAPTER 4")
    print("=" * 60)

    lat = data["latencies"]
    trust = data["trust_scores"]
    billing = data["billing"]
    events = data["events"]

    if not lat.empty:
        all_lat = lat["latency_ms"].dropna()
        print(f"\nTransaction Latency:")
        print(f"  Total transactions:  {len(all_lat)}")
        print(f"  Average:             {all_lat.mean():.1f} ms")
        print(f"  p50:                 {all_lat.quantile(0.50):.1f} ms")
        print(f"  p95:                 {all_lat.quantile(0.95):.1f} ms")
        print(f"  p99:                 {all_lat.quantile(0.99):.1f} ms")
        print(f"  Min:                 {all_lat.min():.1f} ms")
        print(f"  Max:                 {all_lat.max():.1f} ms")

    if not trust.empty:
        max_round = trust["round"].max()
        final = trust[trust["round"] == max_round]
        print(f"\nTrust Scores (final round):")
        for profile in PROFILE_ORDER:
            scores = final[final["profile"] == profile]["trust_score"]
            if len(scores) > 0:
                print(f"  {profile.capitalize():12s}  mean={scores.mean():.3f}  min={scores.min():.3f}  max={scores.max():.3f}")
        above_threshold = final[final["trust_score"] >= 0.7]
        print(f"  Gateways above 0.7 threshold: {len(above_threshold)}/{len(final)}")

    if not events.empty:
        total_uplinks = events["uplink_count"].sum()
        total_errors = events["error_count"].sum()
        total_roaming = events["roaming_count"].sum()
        print(f"\nEvent Statistics:")
        print(f"  Total uplinks:       {total_uplinks}")
        print(f"  Total errors:        {total_errors}")
        print(f"  Error rate:          {total_errors/max(1,total_uplinks)*100:.1f}%")
        print(f"  Roaming events:      {total_roaming}")

    if not billing.empty:
        max_round = billing["round"].max()
        final_billing = billing[billing["round"] == max_round]
        total_charges = final_billing["total_micro"].sum()
        print(f"\nBilling:")
        print(f"  Total charges:       {total_charges} microcents (${total_charges/1_000_000:.4f})")

    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Analyze LoRaWAN Blockchain Evaluation Results")
    parser.add_argument("--results-dir", default="results", help="Directory containing CSV files")
    args = parser.parse_args()

    results_dir = args.results_dir
    figures_dir = os.path.join(results_dir, "figures")
    os.makedirs(figures_dir, exist_ok=True)

    print("Loading data...")
    data = load_data(results_dir)

    print("\nGenerating figures...")
    fig1_trust_convergence(data["trust_scores"], figures_dir)
    fig2_trust_by_profile(data["trust_scores"], figures_dir)
    fig3_latency_distribution(data["latencies"], figures_dir)
    fig4_latency_over_time(data["latencies"], figures_dir)
    fig5_billing_accumulation(data["billing"], figures_dir)
    fig6_settlement_flow(data["billing"], figures_dir)

    print_summary_table(data)

    print(f"\nAll figures saved to {figures_dir}/")


if __name__ == "__main__":
    main()
