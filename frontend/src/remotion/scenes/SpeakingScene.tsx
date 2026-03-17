/**
 * Remotion speaking scene — strategy tip phase, then speech bubble + audio.
 * Two-phase rendering driven by frame number.
 */

import { useCurrentFrame, useVideoConfig, interpolate } from "remotion";
import type { GameScript } from "@/types/game-script";
import type { SpeakingData } from "../timeline";
import PlayerAvatarStatic from "../components/PlayerAvatarStatic";
import AnimatedText from "../components/AnimatedText";
import ExpressionIcon from "@/components/shared/ExpressionIcon";
import FadeTransition from "../components/FadeTransition";

interface SpeakingSceneProps {
  data: SpeakingData;
  durationInFrames: number;
  script: GameScript;
  eliminatedMap: Map<string, string>;
}

const DEATH_LABELS: Record<string, string> = {
  vote: "投票放逐", wolf_kill: "狼人击杀", poison: "女巫毒杀", hunter_shoot: "猎人带走", death_announce: "死亡",
};

export default function SpeakingScene({
  data, durationInFrames, script, eliminatedMap,
}: SpeakingSceneProps) {
  const frame = useCurrentFrame();
  const { fps: _fps } = useVideoConfig();
  const { event, round, tipEndFrame } = data;
  const players = script.players;
  const currentPlayer = players.find((p) => p.id === event.player_id);
  const speechContent = event.action.payload["content"] ?? "";
  const strategyTip = event.strategy_tip ?? "";

  // Phase: tip (frame < tipEndFrame) or speech (frame >= tipEndFrame)
  const isTipPhase = strategyTip && frame < tipEndFrame;
  const isSpeechPhase = frame >= tipEndFrame;

  // Speech bubble fade-in
  const speechOpacity = strategyTip
    ? interpolate(frame, [tipEndFrame, tipEndFrame + 9], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })
    : interpolate(frame, [0, 9], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const speechY = strategyTip
    ? interpolate(frame, [tipEndFrame, tipEndFrame + 9], [10, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })
    : interpolate(frame, [0, 9], [10, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  // Tip bubble fade-in
  const tipOpacity = interpolate(frame, [0, 6], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <FadeTransition durationInFrames={durationInFrames}>
      <div style={{ height: "100%", display: "flex", flexDirection: "column", padding: "39px 57px" }}>
        {/* Avatar row */}
        <div style={{ display: "flex", gap: 29, justifyContent: "center", marginBottom: 29, flexWrap: "wrap" }}>
          {players.map((p) => {
            const isActive = p.id === event.player_id;
            const deathCause = eliminatedMap.get(p.id);
            const isOut = !!deathCause;
            return (
              <div key={p.id} style={{ transform: isActive ? "scale(1.1)" : "scale(1)" }}>
                <PlayerAvatarStatic
                  name={p.name}
                  playerId={p.id}
                  deathCause={deathCause ? DEATH_LABELS[deathCause] ?? deathCause : undefined}
                  size={isActive ? 156 : 130}
                  dimmed={!isActive}
                  eliminated={isOut}
                  word={p.word}
                  role={p.role}
                />
              </div>
            );
          })}
        </div>

        {/* Speech content area */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
          {/* Speaker header */}
          <div style={{ display: "flex", alignItems: "center", gap: 21, marginBottom: 29, opacity: interpolate(frame, [0, 6], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) }}>
            <span style={{ fontSize: 42, fontWeight: "bold", color: "white" }}>{currentPlayer?.name}</span>
            <ExpressionIcon expression={event.expression} size={42} />
            <span style={{ fontSize: 26, color: "#4b5563" }}>第{round}轮</span>
          </div>

          {/* Strategy tip bubble */}
          {strategyTip && (
            <div style={{
              opacity: tipOpacity,
              backgroundColor: "rgba(255,255,255,0.05)",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: 25, padding: "21px 39px",
              maxWidth: 1040, width: "100%", marginBottom: 29,
              maxHeight: 200, overflow: "hidden",
            }}>
              <span style={{ fontSize: 26, color: "#6b7280", marginRight: 10 }}>💭</span>
              <AnimatedText
                text={strategyTip}
                startFrame={0}
                charsPerSecond={15}
                style={{ fontSize: 44, color: "#9ca3af", fontStyle: "italic", lineHeight: 1.5, display: "inline" }}
                showCursor={isTipPhase as boolean}
              />
            </div>
          )}

          {/* Speech bubble — appears after tip finishes */}
          {isSpeechPhase && (
            <div style={{
              opacity: speechOpacity,
              transform: `translateY(${speechY}px)`,
              backgroundColor: "#14141f",
              border: "1px solid #2a2a3a",
              borderRadius: 31, padding: "44px 57px",
              maxWidth: 1300, width: "100%",
              maxHeight: 500, overflow: "hidden",
            }}>
              <AnimatedText
                text={speechContent}
                startFrame={tipEndFrame}
                charsPerSecond={15}
                style={{ fontSize: 50, color: "#e5e7eb", lineHeight: 1.5 }}
              />
            </div>
          )}
        </div>
      </div>
    </FadeTransition>
  );
}
