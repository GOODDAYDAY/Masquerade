/**
 * F-03: Speaking phase — strategy tip (inner monologue) plays first,
 * then speech bubble + audio playback.
 */

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import type { GameEvent, PlayerInfo } from "@/types/game-script";
import PlayerAvatar from "@/components/shared/PlayerAvatar";
import AnimatedText from "@/components/shared/AnimatedText";
import ExpressionIcon from "@/components/shared/ExpressionIcon";
import { useTheater } from "@/components/Theater";

interface SpeakingSceneProps {
  event: GameEvent;
  round: number;
  eventIndex: number;
  players: PlayerInfo[];
  onComplete?: () => void;
}

// Text speed: 15 chars/sec at 1x
const TEXT_SPEED = 15;

export default function SpeakingScene({
  event, round, eventIndex, players, onComplete,
}: SpeakingSceneProps) {
  const { audioManager, speed, eliminatedIds } = useTheater();
  const currentPlayer = players.find((p) => p.id === event.player_id);
  const speechContent = event.action.payload["content"] ?? "";
  const strategyTip = event.strategy_tip ?? "";
  const firedRef = useRef(false);
  const speechBubbleRef = useRef<HTMLDivElement>(null);

  // Phase: "tip" (showing strategy tip) → "speech" (showing speech bubble)
  const [phase, setPhase] = useState<"tip" | "speech">(strategyTip ? "tip" : "speech");

  // Reset phase when event changes
  useEffect(() => {
    setPhase(strategyTip ? "tip" : "speech");
    firedRef.current = false;
  }, [event.player_id, round, eventIndex, strategyTip]);

  // Phase 1: Strategy tip typewriter → then transition to speech
  useEffect(() => {
    if (phase !== "tip" || !strategyTip) return;

    const tipDurationMs = (strategyTip.length / TEXT_SPEED / speed) * 1000 + 500 / speed;
    const timer = setTimeout(() => setPhase("speech"), tipDurationMs);
    return () => clearTimeout(timer);
  }, [phase, strategyTip, speed]);

  // Phase 2: Speech bubble + audio → then onComplete
  useEffect(() => {
    if (phase !== "speech") return;

    // Play audio when speech phase starts
    audioManager?.play(round, eventIndex, event.player_id);

    const audioDurationMs = audioManager?.getDurationMs(round, eventIndex, event.player_id) ?? 0;
    const textDurationMs = (speechContent.length / TEXT_SPEED / speed) * 1000;
    const waitMs = Math.max(audioDurationMs, textDurationMs) + 800 / speed;

    const timer = setTimeout(() => {
      if (!firedRef.current) {
        firedRef.current = true;
        onComplete?.();
      }
    }, waitMs);

    return () => {
      clearTimeout(timer);
      audioManager?.stop();
    };
  }, [phase, audioManager, round, eventIndex, event.player_id, speechContent, speed, onComplete]);

  // Auto-scroll speech bubble as text appears
  useEffect(() => {
    if (phase !== "speech" || !speechBubbleRef.current) return;
    const el = speechBubbleRef.current;
    const interval = setInterval(() => {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }, 200);
    return () => clearInterval(interval);
  }, [phase, speechContent]);

  // Responsive avatar sizing: shrink if too many players for container
  const avatarDefault = { active: 64, inactive: 52 };
  const avatarGap = 12; // gap-3 = 0.75rem ≈ 12px
  const containerWidth = 800; // approximate Theater center panel width
  const totalGap = (players.length - 1) * avatarGap;
  const maxPerPlayer = (containerWidth - totalGap) / players.length;
  const avatarScale = maxPerPlayer >= avatarDefault.inactive ? 1 : maxPerPlayer / avatarDefault.inactive;
  const avatarSize = {
    active: Math.floor(avatarDefault.active * avatarScale),
    inactive: Math.floor(avatarDefault.inactive * avatarScale),
  };

  return (
    <div className="h-full flex flex-col px-6 py-4">
      {/* Avatar row — responsive sizing */}
      <div className="flex gap-3 justify-center mb-3 flex-wrap">
        {players.map((p) => {
          const isActive = p.id === event.player_id;
          const isOut = eliminatedIds.includes(p.id);
          return (
            <div key={p.id} className={`transition-transform ${isActive ? "scale-110" : ""}`}>
              <PlayerAvatar
                name={p.name}
                playerId={p.id}
                size={isActive ? avatarSize.active : avatarSize.inactive}
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
      <div className="flex-1 flex flex-col items-center justify-center min-h-0">
        {/* Speaker header */}
        <motion.div className="flex items-center gap-2 mb-3"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2 }}>
          <span className="text-lg font-bold text-white">{currentPlayer?.name}</span>
          <ExpressionIcon expression={event.expression} size={18} />
          <span className="text-xs text-gray-600">第{round}轮</span>
        </motion.div>

        {/* Strategy tip — inner monologue bubble (shows first, stays visible) */}
        {strategyTip && (
          <motion.div
            className="bg-white/5 border border-white/10 rounded-xl px-4 py-2 max-w-md w-full mb-3 max-h-24 overflow-y-auto"
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

        {/* Speech bubble — only appears after tip finishes, scrollable */}
        {phase === "speech" && (
          <motion.div
            ref={speechBubbleRef}
            className="bg-theater-surface border border-theater-border rounded-2xl px-6 py-5 max-w-xl w-full max-h-48 overflow-y-auto"
            initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
            <AnimatedText text={speechContent} speed={TEXT_SPEED} playbackSpeed={speed}
              className="text-base text-gray-200 leading-relaxed" />
          </motion.div>
        )}
      </div>
    </div>
  );
}
