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
  eliminatedIds: string[];
}

export default function SpeakingScene({
  data, durationInFrames, script, eliminatedIds,
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
    ? interpolate(frame, [tipEndFrame, tipEndFrame + 9], [8, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })
    : interpolate(frame, [0, 9], [8, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  // Tip bubble fade-in
  const tipOpacity = interpolate(frame, [0, 6], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <FadeTransition durationInFrames={durationInFrames}>
      <div style={{ height: "100%", display: "flex", flexDirection: "column", padding: "30px 44px" }}>
        {/* Avatar row */}
        <div style={{ display: "flex", gap: 22, justifyContent: "center", marginBottom: 22, flexWrap: "wrap" }}>
          {players.map((p) => {
            const isActive = p.id === event.player_id;
            const isOut = eliminatedIds.includes(p.id);
            return (
              <div key={p.id} style={{ transform: isActive ? "scale(1.1)" : "scale(1)" }}>
                <PlayerAvatarStatic
                  name={p.name}
                  playerId={p.id}
                  size={isActive ? 120 : 100}
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
          <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 22, opacity: interpolate(frame, [0, 6], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) }}>
            <span style={{ fontSize: 32, fontWeight: "bold", color: "white" }}>{currentPlayer?.name}</span>
            <ExpressionIcon expression={event.expression} size={32} />
            <span style={{ fontSize: 20, color: "#4b5563" }}>第{round}轮</span>
          </div>

          {/* Strategy tip bubble */}
          {strategyTip && (
            <div style={{
              opacity: tipOpacity,
              backgroundColor: "rgba(255,255,255,0.05)",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: 19, padding: "16px 30px",
              maxWidth: 800, width: "100%", marginBottom: 22,
            }}>
              <span style={{ fontSize: 20, color: "#6b7280", marginRight: 8 }}>💭</span>
              <AnimatedText
                text={strategyTip}
                startFrame={0}
                charsPerSecond={15}
                style={{ fontSize: 28, color: "#9ca3af", fontStyle: "italic", lineHeight: 1.5, display: "inline" }}
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
              borderRadius: 24, padding: "34px 44px",
              maxWidth: 1000, width: "100%",
            }}>
              <AnimatedText
                text={speechContent}
                startFrame={tipEndFrame}
                charsPerSecond={15}
                style={{ fontSize: 34, color: "#e5e7eb", lineHeight: 1.5 }}
              />
            </div>
          )}
        </div>
      </div>
    </FadeTransition>
  );
}
