"""
Multi-Agent Root Cause Analysis System
=======================================
Microsoft Agent Framework + Microsoft Foundry (Python)

Sources:
  - https://github.com/microsoft/agent-framework
  - https://github.com/microsoft/agentsleague/tree/main/starter-kits/2-reasoning-agents
  - https://learn.microsoft.com/en-us/agent-framework/

Architecture — WorkflowBuilder with sequential + fan-out/fan-in edges:

                    ┌─────────────────────┐
                    │  SymptomCollector   │  (triage → structured symptoms)
                    └──────────┬──────────┘
                               │ fan-out
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
 ┌────────────────┐  ┌──────────────────┐  ┌────────────────────┐
 │ Hypothesis     │  │ DeploymentChecker│  │  MetricsAnalyzer   │
 │ Generator      │  │ (recent changes) │  │  (time-series)     │
 └───────┬────────┘  └────────┬─────────┘  └─────────┬──────────┘
         └───────────────────►│◄──────────────────────┘
                               │ fan-in
                    ┌──────────▼──────────┐
                    │  EvidenceAnalyzer   │  (scores each hypothesis)
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │  RootCauseReporter  │  (final markdown RCA)
                    └─────────────────────┘

Install:
    pip install agent-framework --pre
    pip install azure-identity

Env vars (choose one pair):
    AZURE_AI_FOUNDRY_PROJECT_ENDPOINT  (e.g. https://<hub>.api.azureml.ms)
    AZURE_AI_FOUNDRY_DEPLOYMENT        (default: gpt-4o)
  OR
    AZURE_OPENAI_ENDPOINT
    AZURE_OPENAI_DEPLOYMENT            (default: gpt-4o)
  OR
    OPENAI_API_KEY                     (falls back to public OpenAI)
"""
import json
import os
from typing import Any
from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    Executor,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowEvent,
    handler,
)
from tools import TOOL_HANDLERS, get_tool_schemas

# ═══════════════════════════════════════════════════════════════════════════════
# CLIENT FACTORY
# ═══════════════════════════════════════════════════════════════════════════════

async def make_client() -> tuple[Any, Any]:
    """
    Create an AzureAIAgentClient from whichever credential is available.
    Priority: Microsoft Foundry → Azure OpenAI → Public OpenAI key.
    """
    # Microsoft Foundry client — import lazily so missing extras give a clear error
    from azure.identity.aio import AzureCliCredential
    from agent_framework.azure import AzureAIAgentClient  # lazy import        
    from dotenv import load_dotenv
    
    load_dotenv()

    foundry = os.getenv("MICROSOFT_FOUNDRY_PROJECT_ENDPOINT")
    modal = os.getenv("MICROSOFT_FOUNDRY_DEPLOYMENT")

    az_oa   = os.getenv("AZURE_OPENAI_ENDPOINT")
    oai_key = os.getenv("OPENAI_API_KEY")

    if foundry:
        print(f"  🔗  Microsoft Foundry  →  {foundry[:60]}…")        
        cred = AzureCliCredential()        
        client = AzureAIAgentClient(project_endpoint=foundry, model_deployment_name=modal,credential=cred, should_cleanup_agent=True)        
        return client, cred
   
    if az_oa:
        print(f"  🔗  Azure OpenAI  →  {az_oa}")
        cred = AzureCliCredential()
        return AzureAIAgentClient(endpoint=az_oa, credential=cred,
                                   should_cleanup_agent=True), cred

    if oai_key:
        print("  🔗  Public OpenAI (dev mode)")
        return AzureAIAgentClient(api_key=oai_key, should_cleanup_agent=True), None

    raise EnvironmentError(
        "Set one of: AZURE_AI_FOUNDRY_PROJECT_ENDPOINT | AZURE_OPENAI_ENDPOINT | OPENAI_API_KEY"
    )

# ═══════════════════════════════════════════════════════════════════════════════
# AGENT FACTORY
# ═══════════════════════════════════════════════════════════════════════════════

def create_agents(client: Any) -> dict[str, Any]:
    """    
    Create all five specialist ChatAgents via AzureAIAgentClient.
    Each agent is registered in Microsoft Foundry as a managed agent resource.
    """   

    # get tool schemas
    tools = get_tool_schemas()

    # sympotom collector agent
    symptom_collector = client.as_agent(
        name="SymptomCollector",
        instructions="""You are a senior SRE specializing in incident triage.

Given a raw incident report, extract and structure ALL observable symptoms.

Steps:
1. List every distinct symptom.
2. Identify affected services/components.
3. Note the timeline (when each symptom started).
4. Classify severity using the classify_severity tool.

Return ONLY a JSON object:
{
  "symptoms": ["<s1>", ...],
  "affected_systems": ["<s>", ...],
  "timeline": "<brief timeline>",
  "severity": "<SEV level>",
  "initial_observations": "<one-paragraph summary>"
}""",
        tools=tools,
    )

    # hypothesis agent
    hypothesis_generator = client.as_agent(
        name="HypothesisGenerator",
        instructions="""You are an expert in distributed-systems failure analysis.

Given structured symptoms, generate 3-5 ranked root-cause hypotheses.
Use the knowledge base and deployment history tools.

Return ONLY JSON:
{
  "hypotheses": [
    {
      "id": "H1",
      "description": "...",
      "supporting_clues": ["..."],
      "likelihood": "High|Medium|Low",
      "confirmation_tests": ["..."]
    }
  ]
}""",
        tools=tools,
    )

    # deployment checker agent
    deployment_checker = client.as_agent(
        name="DeploymentChecker",
        instructions="""You are a change-management specialist.

Given symptoms, retrieve the recent deployment log and identify any changes
that could correlate with the incident timeline.

Return ONLY JSON:
{
  "relevant_deployments": [
    {
      "service": "...",
      "version": "...",
      "time": "...",
      "risk_assessment": "High|Medium|Low",
      "rationale": "..."
    }
  ],
  "change_correlation_summary": "..."
}""",
        tools=tools,
    )

    # metrics analyzer agent
    metrics_analyzer = client.as_agent(
        name="MetricsAnalyzer",
        instructions="""You are a monitoring and observability specialist.

Given symptoms, query all relevant metrics to build a quantitative picture
of the incident. Use query_metric for each relevant metric.

Return ONLY JSON:
{
  "metrics_summary": [
    {"metric": "...", "value": "...", "anomaly": "..."}
  ],
  "quantitative_findings": "...",
  "most_anomalous_metric": "..."
}""",
        tools=tools,
    )

    # evidence analyzer agent
    evidence_analyzer = client.as_agent(
        name="EvidenceAnalyzer",
        instructions="""You are a data-driven incident investigator.

You receive aggregated outputs from: HypothesisGenerator, DeploymentChecker, and MetricsAnalyzer.
Your job: score each hypothesis against the evidence and eliminate unlikely causes.

For each hypothesis assign a confidence score 0-10 and status:
  Confirmed | Likely | Unlikely | Eliminated

Return ONLY JSON:
{
  "evidence_review": [
    {
      "hypothesis_id": "H1",
      "evidence_found": ["..."],
      "confidence_score": 8,
      "status": "Confirmed"
    }
  ],
  "top_candidates": ["H1"],
  "overall_confidence": 85,
  "key_evidence_summary": "..."
}""",
        tools=tools,
    )

    # root cause reported agent
    root_cause_reporter = client.as_agent(
        name="RootCauseReporter",
        instructions="""You are a principal engineer writing a production post-mortem.

Synthesize all findings into a definitive RCA report in Markdown.

## Incident Summary
## Root Cause(s)
## Causal Chain
## Immediate Remediation Steps
## Long-Term Prevention Measures
## Confidence & Caveats

Be precise, factual, and actionable. Avoid filler. End with overall confidence %.""",
        tools=tools,
    )

    return {
        "symptom_collector":    symptom_collector,
        "hypothesis_generator": hypothesis_generator,
        "deployment_checker":   deployment_checker,
        "metrics_analyzer":     metrics_analyzer,
        "evidence_analyzer":    evidence_analyzer,
        "root_cause_reporter":  root_cause_reporter,
    }    

# ═══════════════════════════════════════════════════════════════════════════════
# EXECUTORS  (deterministic workflow nodes — no LLM, just routing/aggregation)
# ═══════════════════════════════════════════════════════════════════════════════

class IncidentIngestionExecutor(Executor):
    """
    START node.  Receives the raw incident text and passes it straight through
    so the first agent gets it.  Also prints a header for visibility.
    """

    def __init__(self):
        super().__init__(id="incident_ingestion")

    @handler
    async def ingest(self, incident: str, ctx: WorkflowContext[str]) -> str:
    #async def ingest(self, incident: str, ctx: WorkflowContext) -> None:
        print("═" * 65)
        print("  🚨  MULTI-AGENT ROOT CAUSE ANALYSIS")
        print("  Stack: Microsoft Agent Framework + Microsoft Foundry")
        print("═" * 65)
        print(f"  🤖  Incident received ({len(incident)} chars) — routing to pipeline…")
        await ctx.send_message(incident)
        return incident


class EvidenceAggregatorExecutor(Executor):
    """
    FAN-IN node.  Waits for outputs from the parallel investigative agents
    (HypothesisGenerator, DeploymentChecker, MetricsAnalyzer) and merges
    them into a single evidence bundle for the EvidenceAnalyzer.
    """

    def __init__(self, expected_inputs: int = 3):
        self.expected_inputs = expected_inputs        
        super().__init__(id="evidence_aggregator")
    
    @handler
    async def aggregate(self, reports: list[Any], ctx: WorkflowContext[str]):
        print(f"  📥  EvidenceAggregator: received {len(reports)} reports")
        texts = []
        for r in reports:
            if isinstance(r, str):
                texts.append(r)
            elif hasattr(r, "messages"):
                parts = []
                for msg in r.messages:
                    for c in msg.contents:
                        if c.type == "text":
                            parts.append(c.text)
                texts.append("\n".join(parts))
            else:
                texts.append(str(r))

        bundle = "\n\n" + ("─" * 50 + "\n\n").join(texts)
        print(f"  ✅  All parallel branches complete — forwarding to EvidenceAnalyzer")
        await ctx.send_message(bundle)

# ═══════════════════════════════════════════════════════════════════════════════
# WORKFLOW BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

def build_rca_workflow(client: Any):
    """
    Constructs the RCA workflow using WorkflowBuilder:

    incident_ingestion
          │
    symptom_collector
          │  fan-out
    ┌─────┼─────┐
    │     │     │
    H     D     M    (HypothesisGenerator | DeploymentChecker | MetricsAnalyzer)
    │     │     │
    └─────┼─────┘
          │  fan-in (evidence_aggregator executor)
    evidence_analyzer
          │
    root_cause_reporter  ← output_response=True
    """
    # Create all agents
    agents = create_agents(client)

    # Create the deterministic executors    
    ingestion   = IncidentIngestionExecutor()
    aggregator  = EvidenceAggregatorExecutor(expected_inputs=3)

    # Get all agents
    symptom_collector     = agents["symptom_collector"]
    hypothesis_generator  = agents["hypothesis_generator"]
    deployment_checker    = agents["deployment_checker"]
    metrics_analyzer      = agents["metrics_analyzer"]
    evidence_analyzer     = agents["evidence_analyzer"]    
    root_cause_reporter   = agents["root_cause_reporter"]       

    # Build workflow and add agents    
    builder =  WorkflowBuilder(
            start_executor=ingestion,
            output_executors=[root_cause_reporter],          
            name="RCA_Pipeline",
            description="4-tier root cause analysis",
        )
    # Ingestion → T1 Symptom Collector
    builder.add_edge(ingestion, symptom_collector)
     # T1 → T2 fan-out (four parallel specialist agents)
    builder.add_fan_out_edges(symptom_collector, [hypothesis_generator, deployment_checker, metrics_analyzer])
    # T2 fan-in → aggregator
    builder.add_fan_in_edges([hypothesis_generator, deployment_checker, metrics_analyzer], aggregator)
    # Aggregator → T3 Evidence Analyzer
    builder.add_edge(aggregator, evidence_analyzer)
    # T3 → T4 Final Reporter
    builder.add_edge(evidence_analyzer, root_cause_reporter)    
    workflow = builder.build()    

    return workflow

# ═══════════════════════════════════════════════════════════════════════════════
# STREAMING RUNNER + TOOL DISPATCH
# ═══════════════════════════════════════════════════════════════════════════════

# Map agent names to display labels
_TIER_LABELS: dict[str, str] = {
    "Symptom_Collector_T1":         "T1",
    "Hypothesis_Generator_T2":      "T2-HG",
    "Deployment_Checker_T2":        "T2-DC",
    "Metrics_Analyzer_T2":          "T2-MA",    
    "Evidence_Analyzer_T3":         "T3",
    "RCAReporter_T4":               "T4",
}


def _unknown_tool(**_) -> str:
    """Fallback used when an agent calls a tool name that is not registered."""
    return "Unknown tool"

async def stream_and_collect(workflow, incident: str) -> str:
    """
    Stream workflow events, dispatch tool calls to local handlers,
    and return the final report text.
    """
    output_chunks = []
    current_executor = None

    # Streaming execution — get events as they happen    
    async for event in await workflow.run(incident, stream=True):
        event: WorkflowEvent  # type annotation for clarity    
        
        # ─────────────────────────────────────────────
        #  AGENT EXECUTION EVENTS (data)
        # ─────────────────────────────────────────────
        if event.type == "data":
            executor_id = getattr(event, "executor_id", None)

            if executor_id and executor_id != current_executor:
                current_executor = executor_id
                label = _TIER_LABELS.get(executor_id, executor_id)

                print(f"\n  🤖  [{label}] {executor_id}")
                print("  " + "─" * 60)

        # ─────────────────────────────────────────────
        #  STREAMED MODEL OUTPUT
        # ─────────────────────────────────────────────
        elif event.type == "output" and event.data is not None:
            d = event.data            
            # 1) If the model is asking you to run tools, do it locally:
            if isinstance(d, AgentResponseUpdate) and getattr(d, "required_action", None):
                tool_outputs = []
                for tc in d.required_action.submit_tool_outputs.tool_calls:                    
                    fn_name = tc.function.name
                    fn_args = json.loads(tc.function.arguments)
                    print(f"\n    🔧  {fn_name}({fn_args})", end="")
                    result = TOOL_HANDLERS.get(fn_name, _unknown_tool)(
                        **fn_args
                    )
                    tool_outputs.append({"tool_call_id": tc.id, "output": str(result)})
                    print(f" → {str(result)[:80]}")
                # Submit results back to the running agent thread
                print(tool_outputs)
                await d.submit_tool_outputs(tool_outputs)
            # 2) Collect textual updates
            # Fast‑path for response updates (most common in streaming)
            if isinstance(d, (AgentResponseUpdate, AgentResponse)):
                text = getattr(d, "text", None)
                if text:
                    output_chunks.append(text)
                else:
                    output_chunks.append(str(d))

            elif isinstance(d, str):
                output_chunks.append(d)
        # ─────────────────────────────────────────────
        #  FAILURES
        # ─────────────────────────────────────────────
        elif event.type == "failed":
            details = getattr(event, "details", None)
            msg = details.message if details else "Unknown error"
            print(f"  ❌  Workflow failed: {msg}")
            break

    return "".join(output_chunks)

