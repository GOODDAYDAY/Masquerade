/**
 * Remotion action scene — strategy tip → action content.
 * Handles night actions (wolf_discuss, protect, seer_check, etc.)
 * and day actions (hunter_shoot, etc.).
 */

import { useCurrentFrame, interpolate } from "remotion";
import type { GameScript } from "@/types/game-script";
import type { ActionData } from "../timeline";
import PlayerAvatarStatic from "../components/PlayerAvatarStatic";
import AnimatedText from "../components/AnimatedText";
import FadeTransition from "../components/FadeTransition";

// Action type -> display label
const ACTION_LABELS: Record<string, string> = {
  protect: "🛡️ 守卫保护",
  wolf_discuss: "🐺 狼人讨论",
  wolf_kill: "🔪 狼人击杀",
  witch_action: "🧪 女巫用药",
  seer_check: "🔮 预言家查验",
  hunter_shoot: "🔫 猎人开枪",
  last_words: "💀 遗言",
  death_announce: "☠️ 死亡公告",
};

const WITCH_USE_LABELS: Record<string, string> = {
  antidote: "使用解药",
  poison: "使用毒药",
  skip: "选择不用药",
};

interface ActionSceneProps {
  data: ActionData;
  durationInFrames: number;
  script: GameScript;
  eliminatedIds: string[];
}

export default function ActionScene({
  data, durationInFrames, script, eliminatedIds,
}: ActionSceneProps) {
  const frame = useCurrentFrame();
  const { event, round, tipEndFrame } = data;
  const players = script.players;
  const currentPlayer = players.find((p) => p.id === event.player_id);

  const actionType = event.action.type;
  const payload = event.action.payload;
  const isNight = event.phase.startsWith("night");
  const label = ACTION_LABELS[actionType] ?? actionType;
  const strategyTip = event.strategy_tip ?? "";

  const textContent = payload["gesture"] ?? payload["content"] ?? "";
  const targetId = payload["target"] ?? payload["target_player_id"] ?? "";
  const targetPlayer = targetId ? players.find((p) => p.id === targetId) : null;
  const witchUse = payload["use"] ?? "";
  const deathNames = payload["deaths"] ?? "";
  const hasText = textContent.length > 0;

  const isTipPhase = strategyTip && frame < tipEndFrame;
  const isContentPhase = frame >= tipEndFrame;

  const tipOpacity = interpolate(frame, [0, 6], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const contentOpacity = strategyTip
    ? interpolate(frame, [tipEndFrame, tipEndFrame + 9], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })
    : interpolate(frame, [0, 9], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const contentY = strategyTip
    ? interpolate(frame, [tipEndFrame, tipEndFrame + 9], [10, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })
    : interpolate(frame, [0, 9], [10, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  const getName = (id: string) => players.find((p) => p.id === id)?.name ?? id;

  const nightBg = isNight ? "rgba(17,24,39,0.4)" : "transparent";
  const cardBg = isNight ? "rgba(31,41,55,0.6)" : "#14141f";
  const cardBorder = isNight ? "#374151" : "#2a2a3a";

  return (
    <FadeTransition durationInFrames={durationInFrames}>
      <div style={{ height: "100%", display: "flex", flexDirection: "column", padding: "39px 57px", backgroundColor: nightBg }}>
        {/* Avatar row */}
        <div style={{ display: "flex", gap: 29, justifyContent: "center", marginBottom: 29, flexWrap: "wrap" }}>
          {players.map((p) => {
            const isActive = p.id === event.player_id;
            const isOut = eliminatedIds.includes(p.id);
            return (
              <div key={p.id} style={{ transform: isActive ? "scale(1.1)" : "scale(1)" }}>
                <PlayerAvatarStatic
                  name={p.name} playerId={p.id}
                  size={isActive ? 156 : 130}
                  dimmed={!isActive} eliminated={isOut}
                  word={p.word} role={p.role}
                />
              </div>
            );
          })}
        </div>

        {/* Action content area */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
          {/* Player name + action label */}
          <div style={{
            display: "flex", alignItems: "center", gap: 21, marginBottom: 29,
            opacity: interpolate(frame, [0, 6], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
          }}>
            {isNight && <span style={{ fontSize: 42 }}>🌙</span>}
            <span style={{ fontSize: 42, fontWeight: "bold", color: "white" }}>{currentPlayer?.name}</span>
            <span style={{ fontSize: 31, color: "#9ca3af" }}>{label}</span>
            <span style={{ fontSize: 26, color: "#4b5563" }}>第{round}轮</span>
          </div>

          {/* Strategy tip */}
          {strategyTip && (
            <div style={{
              opacity: tipOpacity,
              backgroundColor: "rgba(255,255,255,0.05)",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: 25, padding: "21px 39px",
              maxWidth: 1040, width: "100%", marginBottom: 29,
            }}>
              <span style={{ fontSize: 26, color: "#6b7280", marginRight: 10 }}>💭</span>
              <AnimatedText
                text={strategyTip} startFrame={0} charsPerSecond={15}
                style={{ fontSize: 44, color: "#9ca3af", fontStyle: "italic", lineHeight: 1.5, display: "inline" }}
                showCursor={isTipPhase as boolean}
              />
            </div>
          )}

          {/* Action content */}
          {isContentPhase && (
            hasText ? (
              <div style={{
                opacity: contentOpacity,
                transform: `translateY(${contentY}px)`,
                backgroundColor: cardBg,
                border: `1px solid ${cardBorder}`,
                borderRadius: 31, padding: "44px 57px",
                maxWidth: 1300, width: "100%",
              }}>
                <AnimatedText
                  text={textContent}
                  startFrame={tipEndFrame}
                  charsPerSecond={15}
                  style={{ fontSize: 50, color: isNight ? "#d1d5db" : "#e5e7eb", lineHeight: 1.5, fontStyle: isNight ? "italic" : "normal" }}
                />
              </div>
            ) : (
              <div style={{
                opacity: contentOpacity,
                transform: `translateY(${contentY}px)`,
                maxWidth: 910, width: "100%",
                display: "flex", flexDirection: "column", gap: 21,
              }}>
                {/* Target card */}
                {targetPlayer && (
                  <div style={{
                    display: "flex", alignItems: "center", gap: 23,
                    backgroundColor: cardBg, border: `1px solid ${cardBorder}`,
                    borderRadius: 16, padding: "29px 39px",
                  }}>
                    <span style={{ fontSize: 31, color: "#d1d5db", flex: 1 }}>{getName(event.player_id)}</span>
                    <span style={{ fontSize: 26, color: "#4b5563" }}>→</span>
                    <span style={{ fontSize: 31, color: "#6366f1", fontWeight: 500 }}>{targetPlayer.name}</span>
                  </div>
                )}
                {/* Witch action */}
                {witchUse && (
                  <div style={{
                    display: "flex", alignItems: "center", gap: 23,
                    backgroundColor: cardBg, border: `1px solid ${cardBorder}`,
                    borderRadius: 16, padding: "29px 39px",
                  }}>
                    <span style={{ fontSize: 31, color: "#d1d5db", flex: 1 }}>{getName(event.player_id)}</span>
                    <span style={{ fontSize: 26, color: "#4b5563" }}>→</span>
                    <span style={{
                      fontSize: 31, fontWeight: 500,
                      color: witchUse === "antidote" ? "#4ade80" : witchUse === "poison" ? "#ef4444" : "#9ca3af",
                    }}>
                      {WITCH_USE_LABELS[witchUse] ?? witchUse}
                    </span>
                    {witchUse === "poison" && targetPlayer && (
                      <span style={{ fontSize: 31, color: "#ef4444" }}>({targetPlayer.name})</span>
                    )}
                  </div>
                )}
                {/* Death announce */}
                {deathNames && (
                  <div style={{
                    display: "flex", alignItems: "center", gap: 23,
                    backgroundColor: cardBg, border: `1px solid ${cardBorder}`,
                    borderRadius: 16, padding: "29px 39px",
                  }}>
                    <span style={{ fontSize: 31, color: "#ef4444", fontWeight: 500 }}>
                      {deathNames.split(",").map((n: string) => n.trim()).join("、")} 死亡
                    </span>
                  </div>
                )}
                {/* Fallback */}
                {!targetPlayer && !witchUse && !deathNames && (
                  <div style={{ fontSize: 31, color: "#6b7280", textAlign: "center" }}>（无详细信息）</div>
                )}
              </div>
            )
          )}
        </div>
      </div>
    </FadeTransition>
  );
}
