#!/usr/bin/env python3
"""Generate a UML activity diagram for the dashboard pages (Section 4.6)."""

import graphviz

dot = graphviz.Digraph(
    "dashboard_activity",
    format="png",
    engine="dot",
    graph_attr={
        "rankdir": "LR",
        "bgcolor": "white",
        "dpi": "300",
        "pad": "0.8",
        "nodesep": "0.6",
        "ranksep": "1.6",
        "splines": "true",
        "fontname": "Helvetica",
        "size": "14,6!",
    },
    node_attr={
        "fontname": "Helvetica",
        "fontsize": "13",
        "color": "black",
        "fillcolor": "white",
        "style": "filled",
        "penwidth": "1.8",
    },
    edge_attr={
        "color": "black",
        "arrowsize": "0.9",
        "penwidth": "1.4",
        "fontname": "Helvetica",
        "fontsize": "11",
    },
)

# Start node
dot.node("start", "", shape="circle", width="0.4", height="0.4",
         fillcolor="black", style="filled")

# Dashboard page (landing)
dot.node("dashboard",
    "Dashboard Overview\n"
    "───────────────────────\n"
    "Display network-wide KPIs:\n"
    "total gateways, active devices,\n"
    "daily events, pending charges.\n"
    "Show recent event feed.",
    shape="box", style="filled,rounded", margin="0.35,0.2")

# Decision diamond
dot.node("nav", "Navigate\nvia Sidebar", shape="diamond",
         width="1.5", height="1.2",
         fillcolor="white", style="filled", fontsize="11")

# Gateways
dot.node("gateways",
    "Gateway Management\n"
    "───────────────────────\n"
    "Browse gateways on an interactive\n"
    "map or sortable list. Inspect trust\n"
    "scores, location, owner, status,\n"
    "and 7-day forwarding history.",
    shape="box", style="filled,rounded", margin="0.35,0.2")

# Events
dot.node("events",
    "Event Monitoring\n"
    "───────────────────────\n"
    "Stream live LoRaWAN events\n"
    "(uplinks, joins, downlinks) via\n"
    "SSE, or query historical events\n"
    "with type and gateway filters.",
    shape="box", style="filled,rounded", margin="0.35,0.2")

# Billing
dot.node("billing",
    "Billing & Settlements\n"
    "───────────────────────\n"
    "View inter-organisation roaming\n"
    "charges recorded on blockchain.\n"
    "Compare receivables vs payables;\n"
    "inspect charge table or matrix.",
    shape="box", style="filled,rounded", margin="0.35,0.2")

# Flow
dot.edge("start", "dashboard", label="  launch  ")
dot.edge("dashboard", "nav", label="  select page  ")

dot.edge("nav", "gateways", label="  /gateways  ")
dot.edge("nav", "events",   label="  /events  ")
dot.edge("nav", "billing",  label="  /billing  ")

out = dot.render(
    filename="dashboard_activity_diagram",
    directory="/Users/shaddy/Documents/Capstone demo 2/diagrams",
    cleanup=True,
)
print(f"Saved to {out}")
