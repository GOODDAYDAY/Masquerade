/**
 * F-05: Finale — identity reveal, winner, stats. Words always shown.
 */

import { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import type { PlayerInfo, GameResultData } from "@/types/game-script";
import PlayerAvatar from "@/components/shared/PlayerAvatar";

interface FinaleSceneProps {
  result: GameResultData;
  players: PlayerInfo[];
  onComplete?: () => void;
}

function getWinnerDisplay(winner: string, players: PlayerInfo[]): { text: string; colorClass: string } {
  if (winner === "civilian") return { text: "平民阵营获胜", colorClass: "text-theater-accent" };
  if (winner === "spy") return { text: "卧底获胜", colorClass: "text-theater-danger" };
  if (winner === "blank") return { text: "白板获胜", colorClass: "text-gray-300" };
  if (winner === "spy,blank") return { text: "非平民阵营获胜", colorClass: "text-theater-danger" };
  // All-blank or other composite: winner is comma-separated player IDs
  const winnerIds = winner.split(",");
  const names = winnerIds.map((id) => players.find((p) => p.id === id)?.name ?? id);
  return { text: `存活者获胜：${names.join("、")}`, colorClass: "text-gray-300" };
}

export default function FinaleScene({ result, players, onComplete }: FinaleSceneProps) {
  const winnerInfo = getWinnerDisplay(result.winner, players);
  const firedRef = useRef(false);

  const durationSec = Math.round(result.total_duration_ms / 1000);
  const durationMin = Math.floor(durationSec / 60);
  const durationRemSec = durationSec % 60;

  useEffect(() => {
    firedRef.current = false;
    const timer = setTimeout(() => {
      if (!firedRef.current) { firedRef.current = true; onComplete?.(); }
    }, 7000);
    return () => clearTimeout(timer);
  }, [onComplete]);

  return (
    <div className="h-full flex flex-col items-center justify-center px-6">
      <motion.h1 className="text-5xl font-bold text-white mb-8"
        initial={{ opacity: 0, scale: 0.5 }} animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.6, type: "spring" }}>
        游戏结束
      </motion.h1>

      {/* Players with words and roles */}
      <motion.div className="flex gap-5 justify-center mb-8 flex-wrap"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.8, duration: 0.5 }}>
        {players.map((p) => (
          <motion.div key={p.id}
            animate={(p.role === "spy" || p.role === "blank") ? { scale: [1, 1.12, 1], transition: { repeat: 2, duration: 0.4 } } : {}}>
            <PlayerAvatar name={p.name} playerId={p.id} size={52}
              eliminated={result.eliminated_order.includes(p.id)}
              word={p.word} role={p.role} />
          </motion.div>
        ))}
      </motion.div>

      {/* Winner */}
      <motion.p className={`text-3xl font-bold mb-6 ${winnerInfo.colorClass}`}
        initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 1.8, duration: 0.5 }}>
        {winnerInfo.text}
      </motion.p>

      {/* Stats */}
      <motion.div className="grid grid-cols-3 gap-6 text-center"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 2.4, duration: 0.4 }}>
        <div>
          <p className="text-2xl font-bold text-white">{result.total_rounds}</p>
          <p className="text-xs text-gray-500">总轮次</p>
        </div>
        <div>
          <p className="text-2xl font-bold text-white">{result.eliminated_order.length}</p>
          <p className="text-xs text-gray-500">淘汰人数</p>
        </div>
        <div>
          <p className="text-2xl font-bold text-white">
            {durationMin > 0 ? `${durationMin}m${durationRemSec}s` : `${durationSec}s`}
          </p>
          <p className="text-xs text-gray-500">总耗时</p>
        </div>
      </motion.div>
    </div>
  );
}
