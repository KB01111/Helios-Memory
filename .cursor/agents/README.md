# Helios Memory — Local Subagent Swarm

Build the provider-agnostic Helios Memory plugin using **local Cursor subagents** with **Composer 2.5** (`composer-2.5-fast`). No cloud orchestrate kickoff required.

## Quick start

1. Open the Helios-Memory project in Cursor.
2. Start with the planner:

```
Use the helios-planner subagent to plan and coordinate building the full Helios Memory plugin from scratch. Track all 12 deliverables and assign the first wave of workers.
```

3. The planner decomposes work and spawns workers via the Task tool. You can also invoke workers directly.

## Subagents

| Agent | Role |
|-------|------|
| `helios-planner` | Orchestrates build, tracks deliverables, assigns task briefs (does not code) |
| `helios-core-worker` | Pydantic models, config, privacy policy, plugin entrypoint, workflow |
| `helios-providers-worker` | Protocol interfaces, SQLite providers, DB schemas |
| `helios-cloud-worker` | FastFlowLM/Ollama providers, Supabase/Redis stubs |
| `helios-routing-worker` | IntentRouter, MemorySynthesizer, ConsolidationWorker, conflicts, decay |
| `helios-test-worker` | pytest setup and unit tests |
| `helios-docs-worker` | README, config examples, agent integration examples |

## Suggested execution order

```
helios-planner
    ├── Wave 1: helios-core-worker (structure + skeleton)
    │            helios-providers-worker (interfaces + schemas)
    ├── Wave 2: helios-providers-worker (SQLite impl)
    │            helios-routing-worker (router + consolidation)
    │            helios-cloud-worker (FastFlowLM)
    ├── Wave 3: helios-cloud-worker (cloud stubs)
    ├── Wave 4: helios-test-worker
    │            helios-docs-worker
    └── Wave 5: helios-core-worker (integration wiring)
                 helios-planner (final checklist)
```

Run independent workers in parallel when the planner says dependencies are clear.

## Example prompts per worker

### helios-planner
```
Use the helios-planner subagent to assess current repo state, update the 12-deliverable checklist, and assign the next wave of workers.
```

### helios-core-worker
```
Use the helios-core-worker subagent to create the package folder structure, Pydantic config/models, privacy policy module, and HeliosMemoryPlugin skeleton with the full workflow pipeline.
```

### helios-providers-worker
```
Use the helios-providers-worker subagent to implement CacheStore, EpisodicMemoryStore, and VectorArchive Protocols plus SQLite providers and SQL schemas for memories, memory_events, document_chunks, and conflicts.
```

### helios-cloud-worker
```
Use the helios-cloud-worker subagent to implement FastFlowLM and Ollama OpenAI-compatible ReasoningModel providers, plus Supabase/Upstash/Postgres adapter stubs for cloud and hybrid modes.
```

### helios-routing-worker
```
Use the helios-routing-worker subagent to implement rule-based IntentRouter, MemorySynthesizer, async ConsolidationWorker, conflict resolution, and temporal decay.
```

### helios-test-worker
```
Use the helios-test-worker subagent to set up pytest and write unit tests for routing, memory retrieval, conflict resolution, and consolidation.
```

### helios-docs-worker
```
Use the helios-docs-worker subagent to write README.md, config examples for local/cloud/hybrid modes, and agent integration examples.
```

## The 12 deliverables

1. Folder structure
2. Python core (Pydantic, config, privacy, plugin, workflow)
3. Provider interfaces with type hints
4. Local SQLite implementation
5. Cloud-ready Supabase/Postgres stub
6. FastFlowLM OpenAI-compatible provider
7. Config examples (local, cloud, hybrid)
8. DB schema (memories, memory_events, document_chunks, conflicts)
9. Rule-based routing policy
10. Async consolidation worker
11. Unit tests (routing, retrieval, conflicts, consolidation)
12. README with install, run, and agent examples

## Model preference

When spawning workers via Task tool, request **`composer-2.5-fast`**.

## Type checking (pyrefly)

[Pyrefly](https://pyrefly.org/) is the project type checker (Rust-based, PyPI: `pyrefly`).

```bash
pip install -e ".[dev]"
pyrefly check --summarize-errors
```

Or with Hatch: `hatch run typecheck`. Config lives in `[tool.pyrefly]` in `pyproject.toml`.

## Privacy & secrets

- Secrets from environment variables only
- Do not send sensitive files to cloud without explicit user permission
- All subagents work only in this repository
