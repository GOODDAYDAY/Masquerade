# Requirement Index

| ID | Name | Status | Updated | Description |
|:---|:---|:---|:---|:---|
| REQ-001 | Project Init | Completed | 2026-03-14 | Backend skeleton, core interfaces, game registry, spy game engine, agent framework (LangGraph + strategy injection), orchestrator, script module, CLI entry |
| REQ-002 | Spy Integration Test | Completed | 2026-03-14 | Integration test script for spy game: mock LLM, two scenarios (civilian wins / spy wins), script output verification, memory safety |
| REQ-003 | Web Script Replay | Development Done | 2026-03-14 | Web-based game theater: TTS audio gen, cinematic replay with opening/speaking/voting/finale scenes, playback controls |
| REQ-004 | Playback Pipeline Fix & E2E Test | Completed | 2026-03-15 | Fix backend script recording (round/vote/phase bugs), add end-to-end pipeline test with script structure validation |
| REQ-005 | Blank Role Support | Development Done | 2026-03-15 | Add blank role (no word) to spy game: standard+blank mixed mode & all-blank mode, with frontend display support |
| REQ-006 | Werewolf Game | Completed | 2026-03-15
| REQ-007 | Strategy Tip & Speaking Scene UI Polish | Completed | 2026-03-15
| REQ-008 | Generic Concurrent Acceleration Framework | Completed | 2026-03-15
| REQ-009 | Game Quality Fixes & Generalization | Completed | 2026-03-15
| REQ-010 | Frontend Game-Agnostic Refactor | Completed | 2026-03-16
| REQ-011 | Werewolf Prompt Intelligence Upgrade | Completed | 2026-03-16
| REQ-012 | Theater Side Panels — History & Context | Completed | 2026-03-16 | Werewolf game engine: refactor Runner to remove Spy coupling, implement night/day phases with gesture-based communication, 6 roles, role-specific LLM strategies |
| REQ-013 | Remotion Video Rendering | Completed | 2026-03-16 | Replace CDP screencast with Remotion frame-driven rendering: deterministic 2K 60fps MP4 output with perfect audio sync, GPU-accelerated encoding |
| REQ-014 | AI Intelligence & Prompt Upgrade | Completed | 2026-03-17 | Eliminate name bias, enrich personas, deepen strategic reasoning, evidence-based voting, prompt overhaul for all roles |
| REQ-015 | Gameplay Quality Fixes | Completed | 2026-03-17 | Unified node context base class, anti-hallucination, wolf gesture quality, witch save logic, evaluator/optimizer full context injection | Eliminate name bias, enrich personas, deepen strategic reasoning, evidence-based voting, prompt overhaul for all roles |
| REQ-016 | GPU Auto-Select for Video Rendering | Completed | 2026-03-17 | Auto-detect and select optimal GPU for Remotion rendering: NVIDIA discrete > AMD discrete > iGPU > CPU, zero manual config |
| REQ-017 | UI Layout Fix & AI Intelligence Upgrade | Completed | 2026-03-17 | Avatar responsive layout for 12 players, subtitle auto-scroll, and systematic AI speech quality upgrade with meta-knowledge injection |
| REQ-018 | GraphRAG Reasoning for Board Games | Completed | 2026-03-20 | Game Reasoning Graph: structured knowledge graph reasoning for board game AI — shared graph + private overlay + cognitive bias differentiation, integrated into Thinker/Evaluator pipeline |
| REQ-019 | Method as Documentation Refactor | Completed | 2026-03-20 | Refactored 7 backend files to "Method as Documentation" pattern: thinker/evaluator/optimizer nodes, player, llm_client, runner, tts/generate |
| REQ-020 | Game Display Fixes | Completed | 2026-03-20 | Witch antidote target in payload, remove flex-wrap for avatar row, center-align speech text |
