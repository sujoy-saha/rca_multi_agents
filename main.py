import asyncio
import os
from datetime import datetime
from rca_agents import make_client, build_rca_workflow, stream_and_collect

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

async def run_rca(incident_description: str) -> str:
    client, cred = await make_client()

    async with client:
        workflow = build_rca_workflow(client)
        report = await stream_and_collect(workflow, incident_description)              

        # Save report to disk
        out_dir = os.getenv("RCA_OUTPUT_DIR", ".")
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path    = os.path.join(out_dir, f"rca_report_{ts}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# RCA Report — {ts} UTC\n")            
            f.write(f"**Generated:** {ts} UTC\n\n")
            f.write(report)
        print(f"  💾  Report saved: {path}")        

        print("═" * 65)
        print("  ✅  ROOT CAUSE ANALYSIS COMPLETE")
        print("═" * 65)  

    if cred and hasattr(cred, "__aexit__"):
        await cred.__aexit__(None, None, None)

    return report

# ═══════════════════════════════════════════════════════════════════════════════
# DEMO INCIDENT
# ═══════════════════════════════════════════════════════════════════════════════

DEMO_INCIDENT = """
INCIDENT REPORT — Production Outage
Severity: High  |  Time: 2024-01-15 14:28 UTC

Summary:
E-commerce platform experiencing severe degradation. Customer-facing APIs
returning 5xx errors at 12% (baseline: <0.5%). Page load times rose from
200 ms to 4 s+. Checkout is unresponsive for ~30% of users.

Observed symptoms:
- API gateway p99 latency: 120 ms → 3 400 ms at 14:28 UTC
- /api/checkout error rate: 0.3% → 12%
- api-gateway CPU peaked at 94%
- auth-service memory grew 60% → 91% over 2 h
- postgres-primary: 2 000+ waiting connections (max_connections = 200)
- checkout-service: 14 pod restarts, 9 OOMKilled in 30 min

Timeline:
  14:15 UTC — request rate doubled (800 → 1 600 rps)
  14:28 UTC — error-rate alert fired
  14:35 UTC — on-call engineer paged
  14:45 UTC — incident declared

Affected: api-gateway, auth-service, checkout-service, postgres-primary
User impact: ~30% of active sessions
"""

if __name__ == "__main__":
    asyncio.run(run_rca(DEMO_INCIDENT))
