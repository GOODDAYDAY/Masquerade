/**
 * Generic action scene — renders non-speak/vote events.
 * Handles night actions (wolf_discuss, protect, seer_check, etc.)
 * and day actions (hunter_shoot, etc.) with appropriate styling.
 *
 * Two display modes:
 * - Target-only actions (protect, wolf_kill, seer_check): vote-style compact card
 * - Text actions (wolf_discuss gesture): text bubble with typewriter
 *
 * Sequence: strategy tip plays first → then action content appears.
 */

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import type { GameEvent, PlayerInfo } from "@/types/game-script";
import PlayerAvatar from "@/components/shared/PlayerAvatar";
import AnimatedText from "@/components/shared/AnimatedText";
import { useTheater } from "@/components/Theater";

interface ActionSceneProps {
  event: GameEvent;
  round: number;
  eventIndex: number;
  players: PlayerInfo[];
  onComplete?: () => void;
}

// Action type → display label (extensible map)
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

// Witch action → display text
const WITCH_USE_LABELS: Record<string, string> = {
  antidote: "使用解药",
  poison: "使用毒药",
  skip: "选择不用药",
};

const TEXT_SPEED = 15;

export default function ActionScene({
  event, round, /* eventIndex, */ players, onComplete,
}: ActionSceneProps) {
  const { speed, eliminatedIds } = useTheater();
  const currentPlayer = players.find((p) => p.id === event.player_id);
  const firedRef = useRef(false);

  const actionType = event.action.type;
  const payload = event.action.payload;
  const isNight = event.phase.startsWith("night");
  const label = ACTION_LABELS[actionType] ?? actionType;
  const strategyTip = event.strategy_tip ?? "";

  // Extract display content from payload
  const textContent = payload["gesture"] ?? payload["content"] ?? "";
  const targetId = payload["target"] ?? payload["target_player_id"] ?? "";
  const targetPlayer = targetId ? players.find((p) => p.id === targetId) : null;
  const witchUse = payload["use"] ?? "";
  const deathNames = payload["deaths"] ?? "";
  const hasText = textContent.length > 0;

  // Phase: "tip" (showing strategy tip) → "content" (showing action content)
  const [phase, setPhase] = useState<"tip" | "content">(strategyTip ? "tip" : "content");

  // Reset phase when event changes
  useEffect(() => {
    setPhase(strategyTip ? "tip" : "content");
    firedRef.current = false;
  }, [event.player_id, round, strategyTip]);

  // Phase 1: Strategy tip typewriter → then transition to content
  useEffect(() => {
    if (phase !== "tip" || !strategyTip) return;
    const tipDurationMs = (strategyTip.length / TEXT_SPEED / speed) * 1000 + 500 / speed;
    const timer = setTimeout(() => setPhase("content"), tipDurationMs);
    return () => clearTimeout(timer);
  }, [phase, strategyTip, speed]);

  // Phase 2: Action content → then onComplete
  useEffect(() => {
    if (phase !== "content") return;
    const contentDurationMs = hasText
      ? (textContent.length / TEXT_SPEED / speed) * 1000 + 800 / speed
      : 3000 / speed;
    const timer = setTimeout(() => {
      if (!firedRef.current) {
        firedRef.current = true;
        onComplete?.();
      }
    }, contentDurationMs);
    return () => clearTimeout(timer);
  }, [phase, hasText, textContent, speed, onComplete]);

  const getName = (id: string) => players.find((p) => p.id === id)?.name ?? id;

  return (
    <div className={`h-full flex flex-col px-6 py-4 ${isNight ? "bg-gray-900/40" : ""}`}>
      {/* Avatar row */}
      <div className="flex gap-3 justify-center mb-3 flex-wrap">
        {players.map((p) => {
          const isActive = p.id === event.player_id;
          const isOut = eliminatedIds.includes(p.id);
          return (
            <div key={p.id} className={`transition-transform ${isActive ? "scale-110" : ""}`}>
              <PlayerAvatar
                name={p.name}
                playerId={p.id}
                size={isActive ? 64 : 52}
                dimmed={!isActive}
                eliminated={isOut}
                word={p.word}
                role={p.role}
              />
            </div>
          );
        })}
      </div>

      {/* Action content area */}
      <div className="flex-1 flex flex-col items-center justify-center min-h-0">
        {/* Player name + action label */}
        <motion.div className="flex items-center gap-2 mb-3"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2 }}>
          {isNight && <span className="text-lg">🌙</span>}
          <span className="text-lg font-bold text-white">{currentPlayer?.name}</span>
          <span className="text-sm text-gray-400">{label}</span>
          <span className="text-xs text-gray-600">第{round}轮</span>
        </motion.div>

        {/* Strategy tip — plays first, stays visible */}
        {strategyTip && (
          <motion.div
            className="bg-white/5 border border-white/10 rounded-xl px-4 py-2 max-w-md w-full mb-3"
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
          >
            <span className="text-xs text-gray-500 mr-1">💭</span>
            <AnimatedText
              text={strategyTip}
              speed={TEXT_SPEED}
              playbackSpeed={speed}
              className="text-sm text-gray-400 italic leading-relaxed inline"
            />
          </motion.div>
        )}

        {/* Action content — appears after tip finishes */}
        {phase === "content" && (
          hasText ? (
            /* Text content mode: gesture/speech in a bubble */
            <motion.div
              className={`border rounded-2xl px-6 py-5 max-w-xl w-full ${
                isNight ? "bg-gray-800/60 border-gray-700" : "bg-theater-surface border-theater-border"
              }`}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }}
            >
              <AnimatedText
                text={textContent}
                speed={TEXT_SPEED}
                playbackSpeed={speed}
                className={`text-base leading-relaxed ${isNight ? "text-gray-300 italic" : "text-gray-200"}`}
              />
            </motion.div>
          ) : (
            /* Target-only mode: vote-style compact card */
            <motion.div
              className="max-w-sm w-full space-y-2"
              initial={{ opacity: 0, x: -15 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3 }}
            >
              {/* Main action card: player → target */}
              {targetPlayer && (
                <div className={`flex items-center gap-2.5 border rounded-lg px-4 py-3 ${
                  isNight ? "bg-gray-800/60 border-gray-700" : "bg-theater-surface border-theater-border"
                }`}>
                  <span className="text-sm text-gray-300 flex-1">{getName(event.player_id)}</span>
                  <span className="text-gray-600 text-xs">→</span>
                  <span className="text-sm text-theater-accent font-medium">{targetPlayer.name}</span>
                </div>
              )}

              {/* Witch action card */}
              {witchUse && (
                <div className={`flex items-center gap-2.5 border rounded-lg px-4 py-3 ${
                  isNight ? "bg-gray-800/60 border-gray-700" : "bg-theater-surface border-theater-border"
                }`}>
                  <span className="text-sm text-gray-300 flex-1">{getName(event.player_id)}</span>
                  <span className="text-gray-600 text-xs">→</span>
                  <span className={`text-sm font-medium ${
                    witchUse === "antidote" ? "text-green-400"
                    : witchUse === "poison" ? "text-theater-danger"
                    : "text-gray-400"
                  }`}>
                    {WITCH_USE_LABELS[witchUse] ?? witchUse}
                  </span>
                  {witchUse === "poison" && targetPlayer && (
                    <span className="text-sm text-theater-danger">({targetPlayer.name})</span>
                  )}
                </div>
              )}

              {/* Death announce */}
              {deathNames && (
                <div className={`flex items-center gap-2.5 border rounded-lg px-4 py-3 ${
                  isNight ? "bg-gray-800/60 border-gray-700" : "bg-theater-surface border-theater-border"
                }`}>
                  <span className="text-sm text-theater-danger font-medium">
                    {deathNames.split(",").map((n: string) => n.trim()).join("、")} 死亡
                  </span>
                </div>
              )}

              {/* Fallback */}
              {!targetPlayer && !witchUse && !deathNames && (
                <div className="text-sm text-gray-500 text-center">（无详细信息）</div>
              )}
            </motion.div>
          )
        )}
      </div>
    </div>
  );
}
