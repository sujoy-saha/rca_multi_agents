# Multi-Agent Root Cause Analysis System
### Microsoft Agent Framework + Microsoft Foundry

> Inspired by: [microsoft/agentsleague — 2-reasoning-agents starter kit](https://github.com/microsoft/agentsleague/tree/main/starter-kits/2-reasoning-agents)  
> Built with: [microsoft/agent-framework](https://github.com/microsoft/agent-framework)

---

## Architecture

The system uses a **fan-out / fan-in** `WorkflowBuilder` graph — three specialist agents run concurrently, then converge into a single evidence review before producing the final report.

```
                   ┌─────────────────────┐
                   │  IncidentIngestion  │  (Executor — routes incident text)
                   └──────────┬──────────┘
                              │
                   ┌──────────▼──────────┐
                   │  SymptomCollector   │  (ChatAgent — triage + severity)
                   └──────────┬──────────┘
                              │  fan-out (parallel)
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ Hypothesis       │ │ Deployment       │ │ Metrics          │
│ Generator        │ │ Checker          │ │ Analyzer         │
│ (ChatAgent)      │ │ (ChatAgent)      │ │ (ChatAgent)      │
└────────┬─────────┘ └────────┬─────────┘ └────────┬─────────┘
         └────────────────────┼────────────────────┘
                              │  fan-in (EvidenceAggregatorExecutor)
                   ┌──────────▼──────────┐
                   │  EvidenceAnalyzer   │  (ChatAgent — scores hypotheses)
                   └──────────┬──────────┘
                              │
                   ┌──────────▼──────────┐
                   │  RootCauseReporter  │  (ChatAgent — markdown RCA report)
                   └─────────────────────┘
```

### Framework concepts used

| Concept | Where |
|---|---|
| `AzureAIAgentClient` | Creates managed agents in Azure AI Foundry |
| `ChatAgent` | Each of the 5 specialist agents |
| `Executor` + `@handler` | `IncidentIngestion` and `EvidenceAggregator` nodes |
| `WorkflowBuilder` | Composes agents + executors into a graph |
| `.set_start_executor()` | Marks the entry point |
| `.add_edge()` | Sequential edge between nodes |
| `.add_fan_out_edges()` | One-to-many parallel split |
| `.add_fan_in_edges()` | Many-to-one merge |
| `workflow.run_stream()` | Streams `AgentResponseUpdate` + `AgentResponse` |
| `output_response=True` | Marks the terminal node |
| `should_cleanup_agent=True` | Removes Foundry agent resources after run |

---

## Project layout

```
rca_multi_agents/
├── maon.py            ← Main entry point of the program
├── rca_agents.py      ← Main workflow — agents, executors, graph, runner
├── tools.py           ← Tool implementations (swap mocks for real APIs)
├── .env               ← .env and fill in credentials
├── requirements.txt   ← Python dependencies
└── README.md
```

---

## Setup

### 1. Clone / copy this directory

```bash
cd rca_multi_agents
```

### 2. Install dependencies

```bash
pip install agent-framework --pre
pip install azure-identity python-dotenv
```

Or from requirements.txt:

```bash
pip install -r requirements.txt
```

### 3. Configure credentials

```bash
cp .env.template .env
# Edit .env and fill in your endpoint / key
```

**Option A — Azure AI Foundry (recommended):**

1. Go to [ai.azure.com](https://ai.azure.com) and select your V2 project.
2. Copy the **Project Endpoint** from the Overview tab.
3. Set `AZURE_AI_FOUNDRY_PROJECT_ENDPOINT` in `.env`.
4. Authenticate: `az login` (uses `DefaultAzureCredential`).

**Option B — Azure OpenAI:**

```bash
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-4o
```

**Option C — Public OpenAI (dev only):**

```bash
OPENAI_API_KEY=sk-...
```

### 4. Run

```bash
python main.py
```

---

## Plug in real data sources

`tools.py` contains mock implementations with clearly marked replacement points.

"search_knowledge_base":    search_knowledge_base,
"check_recent_deployments": check_recent_deployments,
"query_metric":             query_metric,
"classify_severity":        classify_severity,

| Tool | Purpose | Real integration |
|---|---|---|
| `search_knowledge_base` | Runbook / KB lookup | Azure AI Search, Confluence |
| `check_recent_deployments` | Deployment history | GitHub Actions |
| `query_metric` | Metrics| Prometheus |
| `classify_severity` | SEV-1/2/3 | Rule-based (configurable) |

### Metrics (Prometheus)

```python
import requests

def query_metric(metric_name: str, window_minutes: int = 60) -> str:
    r = requests.get(
        f"{os.environ['PROMETHEUS_URL']}/api/v1/query",
        params={"query": f"avg_over_time({metric_name}[{window_minutes}m])"},
        timeout=10,
    )
    data = r.json()["data"]["result"]
    return json.dumps(data[:5])   # top 5 series
```

### Deployment history (GitHub Actions)

```python
import subprocess, json

def check_recent_deployments(hours: int = 24) -> str:
    result = subprocess.run(
        ["gh", "api", f"/repos/{ORG}/{REPO}/deployments?per_page=20"],
        capture_output=True, text=True,
    )
    return result.stdout
```

### Knowledge base (Azure AI Search)

```python
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential

def search_knowledge_base(query: str) -> str:
    client = SearchClient(
        endpoint=os.environ["AI_SEARCH_ENDPOINT"],
        index_name="runbooks",
        credential=AzureKeyCredential(os.environ["AI_SEARCH_KEY"]),
    )
    results = client.search(query, top=5)
    return "\n".join(r["content"] for r in results)
```

---

## Add more agents

```python
security_agent = client.create_agent(
    name="SecurityAnalyzer",
    instructions="Check if the incident has security or compliance implications...",
    tools=get_tool_schemas(),
)

workflow = (
    WorkflowBuilder()
    # ...existing registrations...
    .register_agent(lambda: security_agent, name="security_analyzer")
    # Run security analysis in parallel with the other three
    .add_fan_out_edges("symptom_collector",
                       ["hypothesis_generator", "deployment_checker",
                        "metrics_analyzer", "security_analyzer"])   # ← add here
    .add_fan_in_edges(
        ["hypothesis_generator", "deployment_checker",
         "metrics_analyzer", "security_analyzer"],                  # ← add here
        "evidence_aggregator")
    # ...rest of edges...
    .build()
)
```

---

## DevUI (local visualization)

```bash
pip install "agent-framework-devui --pre"
agent-framework-devui --module rca_agents --workflow-var workflow
```

Opens a browser UI showing the live graph with streaming traces.

---

## Observability

Add OpenTelemetry tracing:

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor

provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)
# Agent Framework automatically picks up the global tracer provider
```

---

## References

- [Microsoft Agent Framework — GitHub](https://github.com/microsoft/agent-framework)
- [Microsoft Agent Framework — Docs](https://learn.microsoft.com/en-us/agent-framework/)
- [Azure AI Foundry](https://ai.azure.com)
- [AgentsLeague Starter Kits](https://github.com/microsoft/agentsleague/tree/main/starter-kits)
- [Agent Framework Samples](https://github.com/microsoft/Agent-Framework-Samples)
- [Migration from AutoGen](https://learn.microsoft.com/en-us/agent-framework/migration-guide/from-autogen/)
- [Migration from Semantic Kernel](https://learn.microsoft.com/en-us/agent-framework/migration-guide/from-semantic-kernel/)
