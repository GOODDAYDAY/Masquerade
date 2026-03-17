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

/** Compute responsive avatar size so all players fit in one row */
function getAvatarSize(playerCount: number, gap: number, maxRowWidth: number, defaults: { active: number; inactive: number }) {
  const totalGap = (playerCount - 1) * gap;
  const maxInactive = (maxRowWidth - totalGap) / playerCount;
  if (maxInactive >= defaults.inactive) return defaults;
  const scale = maxInactive / defaults.inactive;
  return { inactive: Math.floor(defaults.inactive * scale), active: Math.floor(defaults.active * scale) };
}

/** Estimate text scroll offset for frame-driven auto-scroll */
function getScrollOffset(text: string, startFrame: number, frame: number, fps: number, charsPerSecond: number, fontSize: number, lineHeight: number, bubbleWidth: number, maxHeight: number) {
  const elapsed = Math.max(0, frame - startFrame);
  const visibleChars = Math.min(text.length, Math.floor((elapsed / fps) * charsPerSecond));
  const charsPerLine = Math.max(1, Math.floor(bubbleWidth / fontSize));
  const lineCount = Math.ceil(visibleChars / charsPerLine);
  const textHeight = lineCount * fontSize * lineHeight;
  return textHeight > maxHeight ? -(textHeight - maxHeight) : 0;
}

export default function SpeakingScene({
  data, durationInFrames, script, eliminatedMap,
}: SpeakingSceneProps) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
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

  // Responsive avatar sizing
  const avatarGap = 29;
  const maxRowWidth = 2560 - 57 * 2; // padding: 57px each side
  const sizes = getAvatarSize(players.length, avatarGap, maxRowWidth, { active: 156, inactive: 130 });

  // Speech bubble auto-scroll
  const speechBubbleMaxH = 500;
  const speechBubbleWidth = 1300 - 57 * 2; // maxWidth minus padding
  const speechScroll = getScrollOffset(speechContent, tipEndFrame, frame, fps, 15, 50, 1.5, speechBubbleWidth, speechBubbleMaxH);

  // Tip bubble auto-scroll
  const tipBubbleMaxH = 200;
  const tipBubbleWidth = 1040 - 39 * 2;
  const tipScroll = getScrollOffset(strategyTip, 0, frame, fps, 15, 44, 1.5, tipBubbleWidth, tipBubbleMaxH);

  return (
    <FadeTransition durationInFrames={durationInFrames}>
      <div style={{ height: "100%", display: "flex", flexDirection: "column", padding: "39px 57px" }}>
        {/* Avatar row */}
        <div style={{ display: "flex", gap: avatarGap, justifyContent: "center", marginBottom: 29, flexWrap: "wrap" }}>
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
                  size={isActive ? sizes.active : sizes.inactive}
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
              maxHeight: tipBubbleMaxH, overflow: "hidden",
            }}>
              <div style={{ transform: `translateY(${tipScroll}px)` }}>
                <span style={{ fontSize: 26, color: "#6b7280", marginRight: 10 }}>💭</span>
                <AnimatedText
                  text={strategyTip}
                  startFrame={0}
                  charsPerSecond={15}
                  style={{ fontSize: 44, color: "#9ca3af", fontStyle: "italic", lineHeight: 1.5, display: "inline" }}
                  showCursor={isTipPhase as boolean}
                />
              </div>
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
              maxHeight: speechBubbleMaxH, overflow: "hidden",
            }}>
              <div style={{ transform: `translateY(${speechScroll}px)` }}>
                <AnimatedText
                  text={speechContent}
                  startFrame={tipEndFrame}
                  charsPerSecond={15}
                  style={{ fontSize: 50, color: "#e5e7eb", lineHeight: 1.5 }}
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </FadeTransition>
  );
}
