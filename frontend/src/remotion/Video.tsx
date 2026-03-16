/**
 * Main Remotion composition — reads script + audio, builds timeline,
 * lays out Sequences for each scene with audio at correct positions.
 */

import { useCurrentFrame, useVideoConfig, Sequence, Audio, staticFile } from "remotion";
import type { GameScript, PlayerInfo } from "@/types/game-script";
import type { SceneFrameRange, SpeakingData } from "./timeline";
import OpeningScene from "./scenes/OpeningScene";
import RoundTitle from "./scenes/RoundTitle";
import SpeakingScene from "./scenes/SpeakingScene";
import ActionScene from "./scenes/ActionScene";
import VotingScene from "./scenes/VotingScene";
import FinaleScene from "./scenes/FinaleScene";

// Side panel components (simplified for video — no scrolling, just static lists)
import SpeechHistoryPanel from "./panels/SpeechHistoryPanel";
import ActionHistoryPanel from "./panels/ActionHistoryPanel";

export interface VideoProps {
  script: GameScript;
  scenes: SceneFrameRange[];
  gameId: string;
  /** Show right-side speech history panel (default false) */
  showSpeechHistory?: boolean;
}

/** Compute eliminated player IDs up to a given absolute frame */
function getEliminatedIds(scenes: SceneFrameRange[], currentFrame: number): string[] {
  const ids: string[] = [];
  for (const scene of scenes) {
    if (scene.startFrame > currentFrame) break;
    if (scene.type === "voting") {
      const voteData = scene.scene.data as { voteResult: { eliminated: string | null } };
      if (voteData.voteResult.eliminated) {
        ids.push(voteData.voteResult.eliminated);
      }
    }
  }
  return ids;
}

/** Collect speech events from previous rounds for side panel */
function getSpeechHistory(scenes: SceneFrameRange[], currentFrame: number) {
  const events: { event: GameScript["rounds"][0]["events"][0]; round: number }[] = [];
  // Find current round number
  let currentRound = 0;
  for (const scene of scenes) {
    if (scene.startFrame > currentFrame) break;
    if ("round" in scene.scene.data) {
      currentRound = (scene.scene.data as { round: number }).round;
    }
  }
  for (const scene of scenes) {
    if (scene.startFrame > currentFrame) break;
    if (scene.type === "speaking") {
      const data = scene.scene.data as SpeakingData;
      if (data.round < currentRound) {
        events.push({ event: data.event, round: data.round });
      }
    }
  }
  return events;
}

/** Collect action events from previous rounds for side panel */
function getActionHistory(scenes: SceneFrameRange[], currentFrame: number) {
  const events: { event: GameScript["rounds"][0]["events"][0]; round: number }[] = [];
  let currentRound = 0;
  for (const scene of scenes) {
    if (scene.startFrame > currentFrame) break;
    if ("round" in scene.scene.data) {
      currentRound = (scene.scene.data as { round: number }).round;
    }
  }
  for (const scene of scenes) {
    if (scene.startFrame > currentFrame) break;
    if (scene.type === "action") {
      const data = scene.scene.data as { event: GameScript["rounds"][0]["events"][0]; round: number };
      if (data.round < currentRound) {
        events.push({ event: data.event, round: data.round });
      }
    }
  }
  return events;
}

// Game type labels for header
const GAME_LABELS: Record<string, string> = {
  spy: "谁是卧底",
  werewolf: "狼人杀",
};

export default function Video({ script, scenes, showSpeechHistory = false }: VideoProps) {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const eliminatedIds = getEliminatedIds(scenes, frame);
  const speechHistory = showSpeechHistory ? getSpeechHistory(scenes, frame) : [];
  const actionHistory = getActionHistory(scenes, frame);

  // Gather audio sequences for speaking scenes
  const audioSequences: { startFrame: number; audioFile: string }[] = [];
  for (const scene of scenes) {
    if (scene.type === "speaking") {
      const data = scene.scene.data as SpeakingData;
      if (data.audioFile) {
        audioSequences.push({
          startFrame: scene.startFrame + data.tipEndFrame,
          audioFile: data.audioFile,
        });
      }
    }
  }

  return (
    <div style={{
      width, height, display: "flex", flexDirection: "column",
      backgroundColor: "#0a0a0f", fontFamily: "'Microsoft YaHei', 'Noto Sans SC', sans-serif",
      overflow: "hidden",
    }}>
      {/* Header */}
      <div style={{
        flexShrink: 0, backgroundColor: "rgba(20,20,31,0.8)",
        borderBottom: "1px solid #2a2a3a",
        padding: "16px 30px",
        display: "flex", alignItems: "center", justifyContent: "center",
        gap: 44, fontSize: 24,
      }}>
        {renderHeader(script)}
      </div>

      {/* Main row: left panel | scene | (optional) right panel */}
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        {/* Left panel — action history */}
        <aside style={{
          width: 520, flexShrink: 0,
          borderRight: "1px solid #2a2a3a",
          backgroundColor: "rgba(10,10,15,0.9)",
          display: "flex", flexDirection: "column",
        }}>
          <div style={{ padding: "14px 24px", borderBottom: "1px solid #2a2a3a" }}>
            <span style={{ fontSize: 28, color: "#6b7280", fontWeight: "bold" }}>🎬 行动记录</span>
          </div>
          <div style={{ flex: 1, overflow: "hidden" }}>
            <ActionHistoryPanel events={actionHistory} players={script.players} />
          </div>
        </aside>

        {/* Main scene area — all scenes get a full-size container */}
        <main style={{ flex: 1, position: "relative", overflow: "hidden" }}>
          {scenes.map((scene, idx) => (
            <Sequence key={idx} from={scene.startFrame} durationInFrames={scene.durationInFrames}>
              <div style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%" }}>
                {renderScene(scene, script, eliminatedIds)}
              </div>
            </Sequence>
          ))}
        </main>

        {/* Right panel — speech history (configurable) */}
        {showSpeechHistory && (
          <aside style={{
            width: 520, flexShrink: 0,
            borderLeft: "1px solid #2a2a3a",
            backgroundColor: "rgba(10,10,15,0.9)",
            display: "flex", flexDirection: "column",
          }}>
            <div style={{ padding: "14px 24px", borderBottom: "1px solid #2a2a3a" }}>
              <span style={{ fontSize: 28, color: "#6b7280", fontWeight: "bold" }}>💬 发言记录</span>
            </div>
            <div style={{ flex: 1, overflow: "hidden" }}>
              <SpeechHistoryPanel events={speechHistory} players={script.players} />
            </div>
          </aside>
        )}
      </div>

      {/* Audio sequences — placed at absolute frame positions */}
      {audioSequences.map((a, i) => (
        <Sequence key={`audio-${i}`} from={a.startFrame}>
          <Audio src={staticFile(a.audioFile)} />
        </Sequence>
      ))}
    </div>
  );
}

// --- Header rendering ---

function renderHeader(script: GameScript) {
  const gameType = script.game.type;

  if (gameType === "spy") {
    return <SpyHeader players={script.players} />;
  }

  const label = GAME_LABELS[gameType] ?? gameType;
  return <span style={{ color: "#9ca3af", fontWeight: "bold" }}>{label} · {script.players.length}人局</span>;
}

function SpyHeader({ players }: { players: PlayerInfo[] }) {
  const isAllBlank = players.every((p) => p.role === "blank");
  const civilianWord = players.find((p) => p.role === "civilian")?.word ?? "";
  const spyWord = players.find((p) => p.role === "spy")?.word ?? "";
  const hasBlank = players.some((p) => p.role === "blank");

  if (isAllBlank) {
    return <span style={{ color: "#9ca3af", fontWeight: "bold" }}>全员白板模式（无词）</span>;
  }

  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <span style={{ color: "#6b7280" }}>平民词</span>
        <span style={{ fontWeight: "bold", color: "#6366f1" }}>{civilianWord}</span>
      </div>
      <span style={{ color: "#374151" }}>|</span>
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <span style={{ color: "#6b7280" }}>卧底词</span>
        <span style={{ fontWeight: "bold", color: "#ef4444" }}>{spyWord}</span>
      </div>
      {hasBlank && (
        <>
          <span style={{ color: "#374151" }}>|</span>
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <span style={{ color: "#6b7280" }}>白板</span>
            <span style={{ fontWeight: "bold", color: "#9ca3af" }}>无词</span>
          </div>
        </>
      )}
    </>
  );
}

// --- Scene rendering ---

function renderScene(scene: SceneFrameRange, script: GameScript, eliminatedIds: string[]) {
  switch (scene.type) {
    case "opening":
      return <OpeningScene data={scene.scene.data as import("./timeline").OpeningData} durationInFrames={scene.durationInFrames} />;
    case "round-title":
      return <RoundTitle data={scene.scene.data as import("./timeline").RoundTitleData} durationInFrames={scene.durationInFrames} />;
    case "speaking":
      return <SpeakingScene data={scene.scene.data as SpeakingData} durationInFrames={scene.durationInFrames} script={script} eliminatedIds={eliminatedIds} />;
    case "action":
      return <ActionScene data={scene.scene.data as import("./timeline").ActionData} durationInFrames={scene.durationInFrames} script={script} eliminatedIds={eliminatedIds} />;
    case "voting":
      return <VotingScene data={scene.scene.data as import("./timeline").VotingData} durationInFrames={scene.durationInFrames} script={script} eliminatedIds={eliminatedIds} />;
    case "finale":
      return <FinaleScene data={scene.scene.data as import("./timeline").FinaleData} durationInFrames={scene.durationInFrames} />;
  }
}
