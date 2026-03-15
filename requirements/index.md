# Requirement Index

| ID | Name | Status | Updated | Description |
|:---|:---|:---|:---|:---|
| REQ-001 | Project Init | Completed | 2026-03-14 | Backend skeleton, core interfaces, game registry, spy game engine, agent framework (LangGraph + strategy injection), orchestrator, script module, CLI entry |
| REQ-002 | Spy Integration Test | Completed | 2026-03-14 | Integration test script for spy game: mock LLM, two scenarios (civilian wins / spy wins), script output verification, memory safety |
| REQ-003 | Web Script Replay | Development Done | 2026-03-14 | Web-based game theater: TTS audio gen, cinematic replay with opening/speaking/voting/finale scenes, playback controls |
| REQ-004 | Playback Pipeline Fix & E2E Test | Completed | 2026-03-15 | Fix backend script recording (round/vote/phase bugs), add end-to-end pipeline test with script structure validation |
| REQ-005 | Blank Role Support | Development Done | 2026-03-15 | Add blank role (no word) to spy game: standard+blank mixed mode & all-blank mode, with frontend display support |
| REQ-006 | Werewolf Game | Completed | 2026-03-15
| REQ-007 | Strategy Tip & Speaking Scene UI Polish | Completed | 2026-03-15 | Werewolf game engine: refactor Runner to remove Spy coupling, implement night/day phases with gesture-based communication, 6 roles, role-specific LLM strategies |
