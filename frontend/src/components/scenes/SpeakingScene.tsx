/**
 * F-03: Speaking phase — speech bubble + audio playback.
 * Uses audio duration to determine when to advance.
 */

import { useEffect, useRef } from "react";
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
  const firedRef = useRef(false);

  useEffect(() => {
    firedRef.current = false;

    // Play audio (fire and forget)
    audioManager?.play(round, eventIndex, event.player_id);

    // Calculate wait time = max(audio duration, text duration) + buffer
    const audioDurationMs = audioManager?.getDurationMs(round, eventIndex, event.player_id) ?? 0;
    const textDurationMs = (speechContent.length / TEXT_SPEED / speed) * 1000;
    const waitMs = Math.max(audioDurationMs, textDurationMs) + 800;

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
  }, [audioManager, round, eventIndex, event.player_id, speechContent, speed, onComplete]);

  return (
    <div className="h-full flex flex-col px-6 py-4">
      <div className="flex gap-4 justify-center mb-6 flex-wrap">
        {players.map((p) => {
          const isActive = p.id === event.player_id;
          const isOut = eliminatedIds.includes(p.id);
          return (
            <div key={p.id} className={`transition-transform ${isActive ? "scale-110" : ""}`}>
              <PlayerAvatar
                name={p.name}
                playerId={p.id}
                size={isActive ? 48 : 40}
                dimmed={!isActive}
                eliminated={isOut}
                word={p.word}
                role={p.role}
              />
            </div>
          );
        })}
      </div>

      <div className="flex-1 flex flex-col items-center justify-center min-h-0">
        <motion.div className="flex items-center gap-2 mb-4"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2 }}>
          <span className="text-lg font-bold text-white">{currentPlayer?.name}</span>
          <ExpressionIcon expression={event.expression} size={18} />
          <span className="text-xs text-gray-600">第{round}轮</span>
        </motion.div>

        <motion.div
          className="bg-theater-surface border border-theater-border rounded-2xl px-6 py-5 max-w-xl w-full"
          initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
          <AnimatedText text={speechContent} speed={TEXT_SPEED} playbackSpeed={speed}
            className="text-base text-gray-200 leading-relaxed" />
        </motion.div>
      </div>
    </div>
  );
}
