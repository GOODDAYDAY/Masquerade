/**
 * Unit tests for Remotion frame-driven timeline builder.
 * Verifies AC-2 (scene order), AC-5 (determinism), and FR-2 (timing formulas).
 */

import { describe, it, expect } from "vitest";
import { buildFrameTimeline, msToFrames } from "../timeline";
import type { GameScript } from "@/types/game-script";

// --- Helpers ---

function makeScript(overrides?: Partial<GameScript>): GameScript {
  return {
    game: { type: "spy", config: {}, created_at: "2026-03-16T00:00:00Z" },
    players: [
      { id: "p1", name: "Alice", model: "m", persona: "p", appearance: "a", role: "civilian", word: "cat" },
      { id: "p2", name: "Bob", model: "m", persona: "p", appearance: "a", role: "spy", word: "dog" },
    ],
    rounds: [
      {
        round_number: 1,
        events: [
          {
            player_id: "p1", phase: "speaking", timestamp: "", thinking_duration_ms: 0,
            thinking: "", expression: "neutral",
            action: { type: "speak", player_id: "p1", payload: { content: "Hello world" } },
            strategy_tip: "Be careful",
            memory_snapshot: { private: [], public: [] },
          },
          {
            player_id: "p2", phase: "speaking", timestamp: "", thinking_duration_ms: 0,
            thinking: "", expression: "smile",
            action: { type: "speak", player_id: "p2", payload: { content: "I agree" } },
            memory_snapshot: { private: [], public: [] },
          },
          {
            player_id: "p1", phase: "voting", timestamp: "", thinking_duration_ms: 0,
            thinking: "", expression: "neutral",
            action: { type: "vote", player_id: "p1", payload: { target: "p2" } },
            memory_snapshot: { private: [], public: [] },
          },
          {
            player_id: "p2", phase: "voting", timestamp: "", thinking_duration_ms: 0,
            thinking: "", expression: "neutral",
            action: { type: "vote", player_id: "p2", payload: { target: "p1" } },
            memory_snapshot: { private: [], public: [] },
          },
        ],
        vote_result: { votes: { p1: "p2", p2: "p1" }, eliminated: null },
      },
    ],
    result: { winner: "civilian", eliminated_order: [], total_rounds: 1, total_duration_ms: 30000 },
    ...overrides,
  };
}

const FPS = 30;

// --- Tests ---

describe("msToFrames", () => {
  it("converts ms to frames with ceiling", () => {
    expect(msToFrames(1000, 30)).toBe(30);
    expect(msToFrames(500, 30)).toBe(15);
    expect(msToFrames(100, 30)).toBe(3); // ceil(3.0)
    expect(msToFrames(33, 30)).toBe(1);  // ceil(0.99)
    expect(msToFrames(0, 30)).toBe(0);
  });
});

describe("buildFrameTimeline", () => {
  const script = makeScript();
  const audioDurations = new Map<string, number>();
  const gameId = "test_game";

  it("produces correct scene order: opening → round-title → speaking → voting → finale", () => {
    const { scenes } = buildFrameTimeline(script, audioDurations, FPS, gameId);
    const types = scenes.map((s) => s.type);
    expect(types).toEqual([
      "opening",
      "round-title",
      "speaking",  // p1
      "speaking",  // p2
      "voting",
      "finale",
    ]);
  });

  it("scenes have increasing startFrame and positive durationInFrames", () => {
    const { scenes } = buildFrameTimeline(script, audioDurations, FPS, gameId);
    for (let i = 0; i < scenes.length; i++) {
      expect(scenes[i]!.durationInFrames).toBeGreaterThan(0);
      if (i > 0) {
        expect(scenes[i]!.startFrame).toBeGreaterThan(scenes[i - 1]!.startFrame);
      }
    }
  });

  it("totalFrames equals last scene end", () => {
    const { scenes, totalFrames } = buildFrameTimeline(script, audioDurations, FPS, gameId);
    const last = scenes[scenes.length - 1]!;
    expect(totalFrames).toBe(last.startFrame + last.durationInFrames);
  });

  it("is deterministic — same input always produces same output", () => {
    const r1 = buildFrameTimeline(script, audioDurations, FPS, gameId);
    const r2 = buildFrameTimeline(script, audioDurations, FPS, gameId);
    expect(r1.totalFrames).toBe(r2.totalFrames);
    expect(r1.scenes.length).toBe(r2.scenes.length);
    for (let i = 0; i < r1.scenes.length; i++) {
      expect(r1.scenes[i]!.startFrame).toBe(r2.scenes[i]!.startFrame);
      expect(r1.scenes[i]!.durationInFrames).toBe(r2.scenes[i]!.durationInFrames);
    }
  });

  it("opening duration = playerCount * 300ms + 3000ms", () => {
    const { scenes } = buildFrameTimeline(script, audioDurations, FPS, gameId);
    const opening = scenes[0]!;
    const expectedMs = script.players.length * 300 + 3000;
    expect(opening.durationInFrames).toBe(msToFrames(expectedMs, FPS));
  });

  it("round-title duration = 2100ms", () => {
    const { scenes } = buildFrameTimeline(script, audioDurations, FPS, gameId);
    const rt = scenes.find((s) => s.type === "round-title")!;
    expect(rt.durationInFrames).toBe(msToFrames(2100, FPS));
  });

  it("vote events are excluded from individual scenes but included in voting aggregate", () => {
    const { scenes } = buildFrameTimeline(script, audioDurations, FPS, gameId);
    const voteScenes = scenes.filter((s) => s.type === "voting");
    expect(voteScenes).toHaveLength(1);
    // No individual "vote" action scenes
    const actionScenes = scenes.filter((s) => s.type === "action");
    expect(actionScenes).toHaveLength(0);
  });

  it("speaking scene with audio uses actual audio duration", () => {
    const withAudio = new Map([["1_0_p1", 5000]]); // 5 seconds of audio
    const { scenes } = buildFrameTimeline(script, withAudio, FPS, gameId);
    const speaking = scenes.find((s) => s.type === "speaking")!;
    // Duration should be at least tipDuration + audioDuration
    const tipMs = ("Be careful".length / 15) * 1000 + 500;
    const minMs = tipMs + 5000 + 800;
    expect(speaking.durationInFrames).toBeGreaterThanOrEqual(msToFrames(minMs, FPS));
  });

  it("finale duration = 7000ms", () => {
    const { scenes } = buildFrameTimeline(script, audioDurations, FPS, gameId);
    const finale = scenes.find((s) => s.type === "finale")!;
    expect(finale.durationInFrames).toBe(msToFrames(7000, FPS));
  });

  it("handles script with no result (no finale scene)", () => {
    const noResult = makeScript({ result: null });
    const { scenes } = buildFrameTimeline(noResult, audioDurations, FPS, gameId);
    expect(scenes.find((s) => s.type === "finale")).toBeUndefined();
  });

  it("works at 60fps with proportionally more frames", () => {
    const r30 = buildFrameTimeline(script, audioDurations, 30, gameId);
    const r60 = buildFrameTimeline(script, audioDurations, 60, gameId);
    // 60fps should have roughly 2x the total frames
    expect(r60.totalFrames).toBeGreaterThan(r30.totalFrames * 1.8);
    expect(r60.totalFrames).toBeLessThan(r30.totalFrames * 2.2);
  });
});
