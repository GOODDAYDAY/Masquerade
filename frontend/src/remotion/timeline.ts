/**
 * Frame-driven timeline builder for Remotion video rendering.
 * Converts GameScript + audio durations into a flat list of SceneFrameRange
 * with absolute frame positions. Pure function, no React dependency.
 */

import type {
  GameScript,
  GameInfo,
  PlayerInfo,
  GameEvent,
  VoteResult,
  GameResultData,
} from "@/types/game-script";

// --- Constants ---

/** Characters per second for typewriter animations */
const TEXT_SPEED = 15;
/** Gap between scenes in ms */
const TRANSITION_MS = 500;

// --- Scene data types ---

export interface OpeningData {
  players: PlayerInfo[];
  gameInfo: GameInfo;
}

export interface RoundTitleData {
  round: number;
  phase: string;
}

export interface SpeakingData {
  event: GameEvent;
  round: number;
  eventIndex: number;
  /** Frame (relative to scene start) where tip phase ends and speech begins */
  tipEndFrame: number;
  /** Audio file path relative to public dir, null if no audio */
  audioFile: string | null;
  /** Audio duration in frames */
  audioDurationFrames: number;
}

export interface ActionData {
  event: GameEvent;
  round: number;
  eventIndex: number;
  /** Frame (relative to scene start) where tip phase ends */
  tipEndFrame: number;
  /** Audio file path (for wolf_discuss etc.), null if no audio */
  audioFile: string | null;
  /** Audio duration in frames */
  audioDurationFrames: number;
}

export interface VotingData {
  voteResult: VoteResult;
  events: GameEvent[];
  voterOrder: string[];
}

export interface FinaleData {
  result: GameResultData;
  players: PlayerInfo[];
}

export type SceneData =
  | { type: "opening"; data: OpeningData }
  | { type: "round-title"; data: RoundTitleData }
  | { type: "speaking"; data: SpeakingData }
  | { type: "action"; data: ActionData }
  | { type: "voting"; data: VotingData }
  | { type: "finale"; data: FinaleData };

export interface SceneFrameRange {
  type: SceneData["type"];
  startFrame: number;
  durationInFrames: number;
  scene: SceneData;
}

export interface FrameTimeline {
  scenes: SceneFrameRange[];
  totalFrames: number;
}

// --- Helpers ---

/** Convert milliseconds to frame count, rounding up to ensure no truncation */
export function msToFrames(ms: number, fps: number): number {
  return Math.ceil((ms / 1000) * fps);
}

/** Calculate typewriter duration in ms for a string */
function typewriterMs(text: string): number {
  if (!text) return 0;
  return (text.length / TEXT_SPEED) * 1000;
}

/** Calculate strategy tip phase duration in ms */
function tipDurationMs(strategyTip: string | undefined): number {
  if (!strategyTip) return 0;
  return typewriterMs(strategyTip) + 500;
}

// Action types that map to speaking scenes (have text content + TTS audio)
const SPEECH_ACTION_TYPES = new Set(["speak", "last_words"]);

// --- Main builder ---

/**
 * Build a complete frame timeline from a GameScript.
 *
 * @param script - The game script JSON
 * @param audioDurations - Map of "round_eventIndex_playerId" -> duration in ms
 * @param fps - Target frame rate (default 30)
 * @param gameId - Game ID for audio file paths
 * @returns Scene frame ranges and total frame count
 */
export function buildFrameTimeline(
  script: GameScript,
  audioDurations: Map<string, number>,
  fps: number,
  gameId: string,
): FrameTimeline {
  const scenes: SceneFrameRange[] = [];
  let currentFrame = 0;
  const transitionFrames = msToFrames(TRANSITION_MS, fps);

  function addScene(sceneData: SceneData, durationMs: number): void {
    const durationInFrames = msToFrames(durationMs, fps);
    scenes.push({
      type: sceneData.type,
      startFrame: currentFrame,
      durationInFrames,
      scene: sceneData,
    });
    currentFrame += durationInFrames + transitionFrames;
  }

  // Opening scene: playerCount * 300ms + 3000ms
  const openingMs = script.players.length * 300 + 3000;
  addScene(
    { type: "opening", data: { players: script.players, gameInfo: script.game } },
    openingMs,
  );

  // Rounds
  for (const round of script.rounds) {
    // Round title: 2100ms
    addScene(
      { type: "round-title", data: { round: round.round_number, phase: "round-start" } },
      2100,
    );

    let eventIndex = 0;
    for (const event of round.events) {
      const actionType = event.action.type;

      if (SPEECH_ACTION_TYPES.has(actionType)) {
        // Speaking scene
        const tip = event.strategy_tip ?? "";
        const tipMs = tipDurationMs(tip);
        const tipFrames = msToFrames(tipMs, fps);

        const audioKey = `${round.round_number}_${eventIndex}_${event.player_id}`;
        const audioDurationMs = audioDurations.get(audioKey) ?? 0;
        const audioFrames = msToFrames(audioDurationMs, fps);

        const speechContent = event.action.payload["content"] ?? "";
        const textMs = typewriterMs(speechContent);
        const speechMs = Math.max(audioDurationMs, textMs) + 800;

        const audioFile = audioDurationMs > 0
          ? `audio/${gameId}/${round.round_number}_${eventIndex}_${event.player_id}.mp3`
          : null;

        addScene(
          {
            type: "speaking",
            data: {
              event,
              round: round.round_number,
              eventIndex,
              tipEndFrame: tipFrames,
              audioFile,
              audioDurationFrames: audioFrames,
            },
          },
          tipMs + speechMs,
        );
      } else if (actionType === "vote") {
        // Individual vote events are skipped — handled by VotingScene aggregate
      } else {
        // Action scene (may have audio for wolf_discuss, last_words etc.)
        const tip = event.strategy_tip ?? "";
        const tipMs = tipDurationMs(tip);
        const tipFrames = msToFrames(tipMs, fps);

        const textContent = event.action.payload["gesture"] ?? event.action.payload["content"] ?? "";
        const hasText = typeof textContent === "string" && textContent.length > 0;

        // Check for audio (wolf_discuss gesture descriptions get TTS too)
        const audioKey = `${round.round_number}_${eventIndex}_${event.player_id}`;
        const audioDurationMs = audioDurations.get(audioKey) ?? 0;
        const audioFrames = msToFrames(audioDurationMs, fps);
        const audioFile = audioDurationMs > 0
          ? `audio/${gameId}/${round.round_number}_${eventIndex}_${event.player_id}.mp3`
          : null;

        const contentMs = hasText
          ? Math.max(audioDurationMs, typewriterMs(textContent)) + 800
          : 3000;

        addScene(
          {
            type: "action",
            data: {
              event,
              round: round.round_number,
              eventIndex,
              tipEndFrame: tipFrames,
              audioFile,
              audioDurationFrames: audioFrames,
            },
          },
          tipMs + contentMs,
        );
      }

      eventIndex++;
    }

    // Voting aggregate
    if (round.vote_result) {
      const votingEvents = round.events.filter((e) => e.action.type === "vote");
      const voterOrder = Object.keys(round.vote_result.votes);
      // voterCount * 1200ms + 1000ms (pause) + 2500ms (result)
      const votingMs = voterOrder.length * 1200 + 1000 + 2500;

      addScene(
        {
          type: "voting",
          data: {
            voteResult: round.vote_result,
            events: votingEvents,
            voterOrder,
          },
        },
        votingMs,
      );
    }
  }

  // Finale
  if (script.result) {
    addScene(
      { type: "finale", data: { result: script.result, players: script.players } },
      7000,
    );
  }

  // Total frames = last scene's end (without trailing transition)
  const totalFrames = scenes.length > 0
    ? scenes[scenes.length - 1]!.startFrame + scenes[scenes.length - 1]!.durationInFrames
    : 0;

  return { scenes, totalFrames };
}
