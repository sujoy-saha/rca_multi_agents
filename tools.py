"""
tools.py — Tool implementations for the RCA agent system.

Each function here is exposed to agents as an OpenAI function tool.
The mock implementations are clearly marked; replace them with real
API calls against your monitoring/CMDB/CI-CD systems.
"""

from __future__ import annotations

import json
import os


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE
# ═══════════════════════════════════════════════════════════════════════════════

_KB: dict[str, str] = {
    "cpu":        "High CPU: runaway processes, GC pressure, or sudden traffic spike.",
    "memory":     "Memory exhaustion: leaks, oversized caches, or OOM conditions.",
    "disk":       "Disk issues: full partitions, I/O saturation, or hardware failure.",
    "network":    "Network degradation: packet loss, DNS failures, firewall rule changes.",
    "database":   "DB slowness: missing indexes, lock contention, connection-pool exhaustion.",
    "latency":    "High latency: upstream slowness, N+1 queries, thread starvation.",
    "error_rate": "Elevated errors: bad deployment, downstream outage, or config drift.",
    "timeout":    "Timeouts: overloaded services, slow deps, or misconfigured SLAs.",
    "connection": "Connection-pool exhaustion or misconfigured max_connections.",
    "crash":      "CrashLoopBackOff: OOM kill, missing config, bad probe, dependency failure.",
    "auth":       "Auth failures: expired/rotated credentials, revoked tokens, cert issues.",
    "rate_limit": "Rate-limiting triggered: traffic spike or misconfigured per-IP cap.",
}


def search_knowledge_base(query: str) -> str:
    """Search internal runbooks / knowledge base for failure patterns."""
    # ── REAL IMPLEMENTATION ──────────────────────────────────────────────────
    # Replace with a call to your internal wiki, Confluence, or vector DB:
    #
    #   from azure.search.documents import SearchClient
    #   client = SearchClient(endpoint=AI_SEARCH_ENDPOINT,
    #                          index_name="runbooks",
    #                          credential=AzureKeyCredential(AI_SEARCH_KEY))
    #   results = client.search(query, top=5)
    #   return "\n".join(r["content"] for r in results)
    # ─────────────────────────────────────────────────────────────────────────
    # Compute query_lower once; _KB keys are already lowercase so no .lower() needed on them
    query_lower = query.lower()
    hits = [v for k, v in _KB.items() if k in query_lower]
    return "\n".join(hits) if hits else "No matching KB entries."


# ═══════════════════════════════════════════════════════════════════════════════
# DEPLOYMENT / CHANGE MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

_MOCK_DEPLOYMENTS = [
    {
        "time": "2h ago",
        "service": "api-gateway",
        "version": "v2.4.1",
        "notes": "Updated rate-limiting config — new per-IP cap of 500 rps",
        "author": "ci-bot",
    },
    {
        "time": "6h ago",
        "service": "auth-service",
        "version": "v1.9.3",
        "notes": "Rotated JWT signing keys — rolling restart took 8 min",
        "author": "platform-team",
    },
    {
        "time": "18h ago",
        "service": "data-pipeline",
        "version": "v3.1.0",
        "notes": "Added new ETL job — queries postgres-primary every 30 s",
        "author": "data-team",
    },
]


def check_recent_deployments(hours: int = 24) -> str:
    """Return the deployment log for the last N hours."""
    # ── REAL IMPLEMENTATION ──────────────────────────────────────────────────
    # Replace with a call to your CI/CD system:
    #
    #   GitHub Actions:
    #     gh api /repos/ORG/REPO/deployments?per_page=20
    #
    #   Azure DevOps:
    #     GET https://dev.azure.com/{org}/{project}/_apis/release/deployments
    #
    #   ArgoCD:
    #     argocd app history APP_NAME --output json
    # ─────────────────────────────────────────────────────────────────────────
    return json.dumps(_MOCK_DEPLOYMENTS, indent=2)


# ═══════════════════════════════════════════════════════════════════════════════
# METRICS / MONITORING
# ═══════════════════════════════════════════════════════════════════════════════

_MOCK_METRICS: dict[str, str] = {
    "cpu_utilization":  "Peak 94% on api-gateway at 14:32 UTC; sustained >80% for 45 min.",
    "memory_usage":     "auth-service memory: 60%→91% over 2 h; no GC spike observed.",
    "error_rate":       "Error rate on /api/checkout: 0.3%→12% at 14:28 UTC.",
    "p99_latency":      "p99 latency: 120 ms→3 400 ms at 14:30 UTC.",
    "request_rate":     "Ingress rate doubled (800→1 600 rps) at 14:15 UTC.",
    "db_connections":   "postgres-primary: 2 000+ waiting connections; max_connections=200.",
    "pod_restarts":     "checkout-service: 14 restarts in 30 min; 9× OOMKilled.",
    "network_errors":   "No elevated packet loss detected. DNS resolution healthy.",
    "disk_io":          "Disk I/O within normal range on all nodes.",
}


def query_metric(metric_name: str, window_minutes: int = 60) -> str:
    """Fetch a named metric snapshot from the monitoring system."""
    # ── REAL IMPLEMENTATION ──────────────────────────────────────────────────
    # Prometheus:
    #   import requests
    #   r = requests.get(PROMETHEUS_URL + "/api/v1/query",
    #                    params={"query": f"avg_over_time({metric_name}[{window_minutes}m])"})
    #   return json.dumps(r.json()["data"]["result"])
    #
    # Azure Monitor:
    #   from azure.monitor.query import MetricsQueryClient
    #   client = MetricsQueryClient(DefaultAzureCredential())
    #   ...
    #
    # Datadog:
    #   from datadog_api_client.v1 import MetricsApi
    #   ...
    # ─────────────────────────────────────────────────────────────────────────
    return _MOCK_METRICS.get(metric_name, f"No data available for metric '{metric_name}'.")


# ═══════════════════════════════════════════════════════════════════════════════
# SEVERITY CLASSIFIER
# ═══════════════════════════════════════════════════════════════════════════════

# Pre-built at module level so they are not reconstructed on every classify_severity call
_SEV1_KEYWORDS: frozenset[str] = frozenset(
    {"outage", "down", "unavailable", "data loss", "breach", "corruption"}
)
_SEV2_KEYWORDS: frozenset[str] = frozenset(
    {"degraded", "unresponsive", "elevated", "timeout", "crash",
     "error spike", "oomkilled", "crashloop"}
)


def classify_severity(symptoms: list[str]) -> str:
    """Classify incident severity from a symptom list → SEV-1/2/3."""
    joined = " ".join(symptoms).lower()
    if any(k in joined for k in _SEV1_KEYWORDS):
        return "SEV-1 (Critical) — potential full outage or data integrity risk"
    if any(k in joined for k in _SEV2_KEYWORDS):
        return "SEV-2 (High) — significant user impact, escalate immediately"
    return "SEV-3 (Medium) — partial degradation, monitor closely"


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL REGISTRY (used by event dispatcher in rca_agents.py)
# ═══════════════════════════════════════════════════════════════════════════════

TOOL_HANDLERS: dict[str, callable] = {
    "search_knowledge_base":    search_knowledge_base,
    "check_recent_deployments": check_recent_deployments,
    "query_metric":             query_metric,
    "classify_severity":        classify_severity,
}

# Built once at import time; get_tool_schemas() returns the same list on every call
_TOOL_SCHEMAS: list[dict] = [
        {
            "type": "function",
            "function": {
                "name": "search_knowledge_base",
                "description": "Search internal runbooks for failure patterns by keyword.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string",
                                  "description": "Keyword (e.g. 'cpu', 'memory', 'database')."}
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "check_recent_deployments",
                "description": "Retrieve the deployment change log for the last N hours.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "hours": {"type": "integer",
                                  "description": "Lookback window in hours (default 24)."}
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_metric",
                "description": (
                    "Fetch a named metric snapshot. "
                    "Valid names: cpu_utilization, memory_usage, error_rate, "
                    "p99_latency, request_rate, db_connections, pod_restarts, "
                    "network_errors, disk_io."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "metric_name": {"type": "string",
                                        "description": "Metric identifier (see description)."},
                        "window_minutes": {"type": "integer",
                                           "description": "Time window in minutes (default 60)."},
                    },
                    "required": ["metric_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "classify_severity",
                "description": "Classify incident severity from a list of symptom strings.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symptoms": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of symptom strings.",
                        }
                    },
                    "required": ["symptoms"],
                },
            },
        },
    ]


def get_tool_schemas() -> list[dict]:
    """Return OpenAI-compatible function tool schema list for all tools."""
    return _TOOL_SCHEMAS
