/**
 * TypeScript types mirroring backend/script/schema.py.
 * This is the data contract between Python backend and React frontend.
 */

export interface GameScript {
  game: GameInfo;
  players: PlayerInfo[];
  rounds: RoundData[];
  result: GameResultData | null;
}

export interface GameInfo {
  type: string;
  config: Record<string, unknown>;
  created_at: string;
}

export interface PlayerInfo {
  id: string;
  name: string;
  model: string;
  persona: string;
  appearance: string;
  role: string; // "spy" | "civilian"
  word: string;
}

export interface RoundData {
  round_number: number;
  events: GameEvent[];
  vote_result: VoteResult | null;
}

export interface GameEvent {
  player_id: string;
  phase: "speaking" | "voting";
  timestamp: string;
  thinking_duration_ms: number;
  thinking: string;
  expression: string;
  action: Action;
  memory_snapshot: MemorySnapshot;
}

export interface Action {
  type: string; // "speak" | "vote"
  player_id: string;
  payload: Record<string, string>;
}

export interface VoteResult {
  votes: Record<string, string>;
  eliminated: string | null;
}

export interface GameResultData {
  winner: string;
  eliminated_order: string[];
  total_rounds: number;
  total_duration_ms: number;
}

export interface MemorySnapshot {
  private: string[];
  public: string[];
}

/** Validate that a JSON object has the minimum required GameScript shape */
export function isValidGameScript(data: unknown): data is GameScript {
  if (!data || typeof data !== "object") return false;
  const obj = data as Record<string, unknown>;
  return (
    obj.game != null &&
    typeof obj.game === "object" &&
    Array.isArray(obj.players) &&
    Array.isArray(obj.rounds)
  );
}
