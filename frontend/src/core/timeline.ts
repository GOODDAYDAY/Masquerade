/**
 * Timeline controller — converts GameScript into a linear scene list
 * and manages playback state. Pure logic, no React dependency.
 */

import type {
  GameScript,
  GameInfo,
  PlayerInfo,
  GameEvent,
  VoteResult,
  GameResultData,
} from "@/types/game-script";

// --- Scene types ---

export type Scene =
  | OpeningScene
  | RoundTitleScene
  | SpeakingScene
  | VotingScene
  | FinaleScene;

export interface OpeningScene {
  type: "opening";
  players: PlayerInfo[];
  gameInfo: GameInfo;
}

export interface RoundTitleScene {
  type: "round-title";
  round: number;
  phase: "speaking" | "voting";
}

export interface SpeakingScene {
  type: "speaking";
  event: GameEvent;
  round: number;
  eventIndex: number;
}

export interface VotingScene {
  type: "voting";
  voteResult: VoteResult;
  round: number;
  events: GameEvent[];
}

export interface FinaleScene {
  type: "finale";
  result: GameResultData;
  players: PlayerInfo[];
}

// --- Scene durations (ms at 1x speed) ---

const SCENE_DURATION: Record<Scene["type"], number> = {
  opening: 8000,
  "round-title": 2500,
  speaking: 6000,
  voting: 8000,
  finale: 10000,
};

// --- Build scene list from script ---

export function buildSceneList(script: GameScript): Scene[] {
  const scenes: Scene[] = [];

  // Opening
  scenes.push({
    type: "opening",
    players: script.players,
    gameInfo: script.game,
  });

  // Rounds
  for (const round of script.rounds) {
    // Use action.type instead of phase — phase field from engine can be inaccurate
    const speakingEvents = round.events.filter((e) => e.action.type === "speak");
    const votingEvents = round.events.filter((e) => e.action.type === "vote");

    // Speaking phase title
    if (speakingEvents.length > 0) {
      scenes.push({
        type: "round-title",
        round: round.round_number,
        phase: "speaking",
      });

      let eventIndex = 0;
      for (const event of speakingEvents) {
        scenes.push({
          type: "speaking",
          event,
          round: round.round_number,
          eventIndex,
        });
        eventIndex++;
      }
    }

    // Voting phase
    if (round.vote_result) {
      scenes.push({
        type: "round-title",
        round: round.round_number,
        phase: "voting",
      });

      scenes.push({
        type: "voting",
        voteResult: round.vote_result,
        round: round.round_number,
        events: votingEvents,
      });
    }
  }

  // Finale
  if (script.result) {
    scenes.push({
      type: "finale",
      result: script.result,
      players: script.players,
    });
  }

  return scenes;
}

// --- Timeline controller ---

export type TimelineListener = {
  onSceneChange?: (scene: Scene, index: number) => void;
  onPlayStateChange?: (isPlaying: boolean) => void;
  onComplete?: () => void;
};

export class TimelineController {
  private scenes: Scene[];
  private _currentIndex = 0;
  private _isPlaying = false;
  private _speed = 1;
  private _timer: ReturnType<typeof setTimeout> | null = null;
  private _sceneCompleted = false;
  private listeners: TimelineListener[] = [];

  constructor(script: GameScript) {
    this.scenes = buildSceneList(script);
  }

  get currentIndex(): number {
    return this._currentIndex;
  }

  get currentScene(): Scene | undefined {
    return this.scenes[this._currentIndex];
  }

  get isPlaying(): boolean {
    return this._isPlaying;
  }

  get speed(): number {
    return this._speed;
  }

  get totalScenes(): number {
    return this.scenes.length;
  }

  get progress(): number {
    if (this.scenes.length <= 1) return 0;
    return this._currentIndex / (this.scenes.length - 1);
  }

  /** Get all scenes for progress bar / round list */
  getScenes(): readonly Scene[] {
    return this.scenes;
  }

  addListener(listener: TimelineListener): () => void {
    this.listeners.push(listener);
    return () => {
      this.listeners = this.listeners.filter((l) => l !== listener);
    };
  }

  play(): void {
    if (this._isPlaying) return;
    this._isPlaying = true;
    this._notifyPlayState();
    // If previous scene already completed, advance to next
    if (this._sceneCompleted) {
      this._advance();
    }
  }

  pause(): void {
    if (!this._isPlaying) return;
    this._isPlaying = false;
    this._clearTimer();
    this._notifyPlayState();
  }

  setSpeed(speed: number): void {
    this._speed = speed;
  }

  seekToScene(index: number): void {
    if (index < 0 || index >= this.scenes.length) return;
    this._clearTimer();
    this._currentIndex = index;
    this._sceneCompleted = false;
    this._notifySceneChange();
  }

  /** Called by scene components when their animation/display is complete */
  markSceneComplete(): void {
    // Guard: prevent double-fire (e.g. framer-motion exit triggering onComplete again)
    if (this._sceneCompleted) return;
    this._sceneCompleted = true;
    if (this._isPlaying) {
      this._clearTimer();
      const delay = 500 / this._speed;
      this._timer = setTimeout(() => this._advance(), delay);
    }
  }

  /** Auto-advance to next scene with delay based on scene type */
  startAutoPlay(): void {
    this._isPlaying = true;
    this._notifyPlayState();
    this._scheduleAutoAdvance();
  }

  private _scheduleAutoAdvance(): void {
    if (!this._isPlaying) return;
    const scene = this.currentScene;
    if (!scene) return;
    const duration = SCENE_DURATION[scene.type] / this._speed;
    this._timer = setTimeout(() => this._advance(), duration);
  }

  private _advance(): void {
    this._sceneCompleted = false;
    if (this._currentIndex >= this.scenes.length - 1) {
      this._isPlaying = false;
      this._notifyPlayState();
      this.listeners.forEach((l) => l.onComplete?.());
      return;
    }
    this._currentIndex++;
    this._notifySceneChange();
  }

  private _clearTimer(): void {
    if (this._timer) {
      clearTimeout(this._timer);
      this._timer = null;
    }
  }

  private _notifySceneChange(): void {
    const scene = this.currentScene;
    if (scene) {
      this.listeners.forEach((l) => l.onSceneChange?.(scene, this._currentIndex));
    }
  }

  private _notifyPlayState(): void {
    this.listeners.forEach((l) => l.onPlayStateChange?.(this._isPlaying));
  }

  destroy(): void {
    this._clearTimer();
    this.listeners = [];
  }
}
