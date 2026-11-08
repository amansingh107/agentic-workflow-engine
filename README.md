# Autonomous Agentic Workflow Engine

An asynchronous, resilient, self-healing multi-agent workflow engine built with **LangGraph**, **Docker SDK**, **PostgreSQL**, **Redis**, and **FastAPI**.

Designed for enterprise-grade autonomous computational workflows with durable checkpointing, sandboxed code execution, and human-in-the-loop governance.

---

## 🎯 Resume Highlights & Key Engineering Claims

This project was built directly to demonstrate production-grade AI systems engineering:

- **Architected cyclic multi-agent workflows in LangGraph with PostgreSQL checkpointing for state persistence.**
- **Built sandboxed code execution via Docker SDK with strict CPU/memory limits and 30s timeout guards.**
- **Implemented human-in-the-loop approval gates via async FastAPI endpoints to pause and resume threads.**

---

## 🏗️ System Architecture

```mermaid
flowchart TD
    Client["Client / Web Dashboard / CLI"] -->|HTTP / SSE| API["FastAPI Async Gateway"]
    API -->|Manage Threads & Resumptions| Engine["LangGraph StateGraph Engine"]
    
    subgraph Storage ["State Persistence & Message Bus"]
        PG[("PostgreSQL\n(LangGraph Checkpointer)")]
        Redis[("Redis\n(Pub/Sub Event Stream)")]
    end

    Engine <-->|Durable Snapshots| PG
    Engine -->|Publish Real-time Events| Redis
    Redis -->|SSE Stream| Client

    subgraph MultiAgentLoop ["Cyclic Multi-Agent Graph"]
        Planner["Planner Agent\n(Sub-goal decomposition)"] --> Coder["Coder Agent\n(Code Synthesis)"]
        Coder --> Guard["Guardrail Agent\n(AST & Heuristic Analysis)"]
        
        Guard -->|Risk Score >= 0.6| Gate{"HITL Approval Gate\n(LangGraph Interrupt)"}
        Gate -->|Approved| Sandbox["Docker Sandbox Engine"]
        Gate -->|Rejected / Edit| Coder
        
        Guard -->|Low Risk| Sandbox
        
        Sandbox --> Critic["Critic / Evaluator Agent\n(Execution Review)"]
        Critic -->|Runtime Error / Stderr| Coder
        Critic -->|Success| Complete["Workflow Completed"]
    end

    subgraph SandboxEnv ["Isolated Docker Environment"]
        Container["Ephemeral Python Container\n- CPU: 0.5 Cores (50k quota)\n- Memory: 256MB Hard Ceiling\n- Network: None (Air-gapped)\n- 30s Watchdog SIGKILL"]
    end

    Sandbox <-->|Docker SDK (docker-py)| SandboxEnv
```

---

## 🔬 Core Components Deep Dive

### 1. Cyclic Multi-Agent Workflow Core (`src/agents/`)
- **State Schema (`AgentState`)**: Typed state tracking task specification, plan steps, synthesized code, execution telemetry (`stdout`, `stderr`, `exit_code`), iteration retry counter, and HITL governance flags.
- **Planner Node**: Decomposes high-level instructions into sequential sub-goals.
- **Coder Node**: Generates runnable Python scripts and incorporates traceback diagnostics in self-healing retry cycles.
- **Guardrail Node**: Static AST parsing detecting dangerous system calls (`os.system`, `subprocess`, `eval`, `exec`, socket connections) and calculating risk scores.
- **Critic Node**: Evaluates sandbox results; triggers self-healing cycles if runtime errors or timeouts occur, bounded by a strict `max_iterations` guard.

### 2. Isolated Sandboxed Execution Engine (`src/sandbox/`)
- **Docker SDK Engine (`DockerSandbox`)**:
  - `cpu_quota=50000`, `cpu_period=100000`: Caps container compute to 0.5 CPU core.
  - `mem_limit="256m"`, `memswap_limit="256m"`: Disables swap and sets hard 256MB ceiling to prevent RAM exhaustion.
  - `network_mode="none"`: Complete network isolation preventing SSRF or credential exfiltration.
  - `read_only=True` with ephemeral tmpfs: Prevents root filesystem modification.
  - **30-Second Watchdog**: Asynchronous timer issuing SIGKILL if scripts hang in infinite loops.
  - Guaranteed ephemeral cleanup in `finally` blocks to eliminate orphaned containers.
- **Local Fallback Sandbox (`LocalProcessSandbox`)**: Subprocess runner with active memory monitoring and timeout guards for development environments without an active Docker daemon.

### 3. State Persistence & Checkpointing (`src/persistence/`)
- Powered by `langgraph.checkpoint.postgres` (`PostgresSaver` / `AsyncPostgresSaver`).
- Workflows are indexed by `thread_id`. State snapshots are persisted at every node boundary.
- If worker processes restart, workflows resume with full historical context.
- Fallback `MemorySaver` supported for lightweight testing.

### 4. Human-in-the-Loop (HITL) Approval Gates (`src/api/`)
- Uses LangGraph's native `interrupt()` primitive.
- Suspends thread execution when code risk score exceeds safety thresholds.
- Exposes approval state via `GET /api/v1/workflows/{thread_id}` and accepts operator decisions (`APPROVE`, `REJECT`, `EDIT_CODE`) via `POST /api/v1/workflows/{thread_id}/resume`.

### 5. Interactive Real-Time Dashboard (`src/ui/dashboard.html`)
- Clean Tailwind CSS web interface served directly by FastAPI at `http://localhost:8000/`.
- Live visualizer of graph node transitions, synthesized code, sandbox telemetry, and an interactive HITL approval banner.

---

## 🚀 Quickstart Guide

### Option A: Local Virtual Environment

1. **Activate Environment & Install Dependencies**:
   ```bash
   python -m venv .venv
   .\.venv\Scripts\activate  # Windows
   pip install -r requirements.txt
   ```

2. **Configure Environment Variables**:
   ```bash
   cp .env.example .env
   # Add your Google Gemini or OpenAI API key (or leave empty to run with deterministic MockLLM)
   ```

3. **Run the FastAPI Server & Dashboard**:
   ```bash
   uvicorn src.api.app:app --reload --port 8000
   ```
   Open your browser at **`http://localhost:8000`** to access the interactive dashboard!

### Option B: Full Docker Compose Deployment

Spins up PostgreSQL 16, Redis 7, and the Agentic Workflow API container:
```bash
cd docker
docker compose up --build
```

---

## 🧪 Comprehensive Test Suite

The engine features 21 automated unit and integration tests across sandboxing, graph convergence, checkpointing, and REST endpoints:

```bash
pytest tests/ -v
```

Test coverage includes:
- **`test_sandbox.py`**: Clean execution, syntax errors, zero division errors, infinite loop 30s timeout watchdog, and memory bomb exhaustion termination.
- **`test_graph.py`**: AST security analyzer, planner parsing, end-to-end graph convergence, and max iteration recursion guard.
- **`test_checkpoint_and_hitl.py`**: State persistence, snapshot history inspection, interrupt pause on security risk, and resume with approval/rejection.
- **`test_api.py`**: Health check, workflow initiation, status querying, HITL resumption via HTTP, and dashboard rendering.

---

## 🎓 Technical Interview Defense & Architectural Q&A

When discussing this project in Machine Learning & AI Engineering interviews, use these talking points:

### Q1: Why did you choose LangGraph over AutoGen or CrewAI?
> **Answer**: AutoGen and CrewAI are conversational multi-agent frameworks optimized for open-ended chat, but they lack deterministic control flow, fine-grained state machines, and native checkpointing. LangGraph models workflows as explicit directed graphs (`StateGraph`) with typed states and conditional routing. This makes cyclic loops (Coder $\leftrightarrow$ Critic), deterministic human-in-the-loop interrupts, and durable database persistence straightforward to engineer and audit.

### Q2: Why PostgreSQL for checkpointing instead of Redis or in-memory state?
> **Answer**: In-memory state is ephemeral; if a worker restarts or crashes midway through a long-running workflow, all execution progress and thread history are lost. Redis is great for ephemeral caching and Pub/Sub streaming, but PostgreSQL provides ACID-compliant relational storage for durable state snapshots. LangGraph stores state transitions with thread IDs and checkpoint namespaces, enabling thread recovery, audit logging, and state time-travel.

### Q3: What are the security risks of letting an LLM execute arbitrary code, and how did you mitigate them?
> **Answer**: Allowing an LLM to generate and run arbitrary code presents severe attack vectors: host filesystem destruction, container escape, cryptocurrency mining, and network exfiltration (SSRF). 
> We implemented defense-in-depth:
> 1. **Static AST Analysis**: Scans syntax trees before execution to catch unauthorized OS/subprocess calls.
> 2. **Docker cgroups**: Caps memory at 256MB (swap disabled) and CPU quota at 0.5 cores.
> 3. **Network Isolation**: `network_mode="none"` prevents external outbound connections.
> 4. **Read-Only Root Filesystem**: Only ephemeral `/tmp` tmpfs is writable.
> 5. **Timeout Watchdog**: An active 30s watchdog triggers SIGKILL on runaway loops.

### Q4: How does Human-in-the-Loop work with asynchronous REST APIs?
> **Answer**: LangGraph provides an `interrupt()` primitive. When a node detects elevated risk, calling `interrupt()` halts execution and serializes the exact memory checkpoint to PostgreSQL. FastAPI reports the thread status as `is_paused = True` with the interrupt payload. When a human submits `POST /workflows/{thread_id}/resume`, FastAPI passes a `Command(resume=...)` object into `workflow_app.invoke()`, deserializing the checkpoint from PostgreSQL and resuming execution without re-running previous steps.

---

## 📁 Repository Structure

```text
agentic-workflow/
├── docker/
│   ├── Dockerfile.api          # Container for FastAPI workflow engine
│   ├── Dockerfile.sandbox      # Hardened container for Python sandbox execution
│   └── docker-compose.yml      # Orchestration for PostgreSQL, Redis, and API
├── src/
│   ├── config.py               # Centralized Pydantic settings
│   ├── agents/
│   │   ├── state.py            # TypedDict AgentState schema
│   │   ├── llm.py              # LLM factory (Gemini, OpenAI, MockLLM)
│   │   ├── graph.py            # LangGraph StateGraph & conditional routing
│   │   └── nodes/              # Specialized agent nodes
│   │       ├── planner.py      # Decomposes tasks into sub-goals
│   │       ├── coder.py        # Synthesizes Python code with error correction
│   │       ├── guardrail.py    # AST static security analyzer
│   │       ├── approval.py     # LangGraph interrupt() approval gate
│   │       ├── sandbox_node.py # Sandbox invocation node
│   │       └── critic.py       # Evaluates stdout/errors for cyclic self-healing
│   ├── sandbox/
│   │   ├── base.py             # ExecutionResult & BaseSandbox interface
│   │   ├── docker_runner.py    # Docker SDK runner (cgroups, 30s watchdog)
│   │   ├── process_runner.py   # Subprocess fallback runner
│   │   └── factory.py          # Auto-detection sandbox factory
│   ├── persistence/
│   │   └── checkpointer.py     # PostgreSQL & Memory checkpointing
│   ├── api/
│   │   ├── app.py              # FastAPI application instance & CORS
│   │   ├── routes.py           # REST endpoints (start, resume, history, SSE)
│   │   └── events.py           # Redis Pub/Sub & in-memory event bus
│   └── ui/
│       └── dashboard.html      # Real-time interactive Tailwind CSS web dashboard
├── tests/
│   ├── test_sandbox.py         # Sandbox timeout & memory tests
│   ├── test_graph.py           # Cyclic agent execution tests
│   ├── test_checkpoint_and_hitl.py # PostgreSQL persistence & HITL tests
│   └── test_api.py             # FastAPI endpoint & dashboard tests
├── .env.example
├── requirements.txt
└── README.md
```
