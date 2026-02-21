# Factory Audit Log
## Project: factory-control-bot
- **Created**: 2026-02-21
- **Pipeline Start**: 2026-02-21

---

## Phase 0: Complexity Assessment
- **Timestamp**: 2026-02-21
- **Model**: Claude Opus 4.6 (native, Orchestrator)
- **Tier Selected**: TIER 3 — Complex Project

### Rationale
| Signal | Value | Threshold |
|--------|-------|-----------|
| Endpoints/features | 20+ | >20 = Tier 3 |
| DB entities | 7 tables | Multiple |
| External integrations | 8+ (Telegram, Groq, OpenAI, Docker, tmux, GitHub, nginx, certbot) | Multiple |
| Real-time needs | Yes (live log streaming) | Yes = Tier 3 |
| Auth complexity | Whitelist + admin roles | Complex |
| Multi-service | Bot + PostgreSQL + Docker + 4 engines | Multi-service |

### Tier 3 Model Assignments
| Role | Model | Provider | Via |
|------|-------|----------|-----|
| Orchestrator | Claude Opus 4.6 | Anthropic | Native |
| Requirements Analyst | Gemini 3 Pro | Google | zen MCP |
| Architect | Claude Opus 4.6 | Anthropic | Native |
| Backend Implementer | Claude Sonnet 4.6 | Anthropic | Task tool |
| Frontend Implementer | Gemini 3 Pro | Google | zen MCP |
| Black Box Tester | GPT-5.2 | OpenAI | zen MCP |
| Code Reviewer | O3 | OpenAI | zen MCP |
| Security Auditor (primary) | Gemini 3 Pro | Google | zen MCP |
| Security Auditor (secondary) | GLM-5 | Zhipu AI | zen MCP |
| Research Agent | Sonar Deep Research | Perplexity | Perplexity MCP |
| Full Context Review | Kimi 2.5 | Moonshot | zen MCP |
| Docs and Deployer | Claude Sonnet 4.6 | Anthropic | Task tool |

- **Est. external API cost**: $40-80
- **Tokens (Phase 0)**: ~2,000 input (native)
- **Decision**: Proceed with Tier 3 pipeline

---
