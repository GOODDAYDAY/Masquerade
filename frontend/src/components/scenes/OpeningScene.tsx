/**
 * F-02: Opening scene — game title, player cards with words and roles.
 */

import { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import type { PlayerInfo, GameInfo } from "@/types/game-script";
import PlayerAvatar from "@/components/shared/PlayerAvatar";

const GAME_TITLES: Record<string, string> = {
  spy: "谁是卧底",
  werewolf: "狼人杀",
};

interface OpeningSceneProps {
  players: PlayerInfo[];
  gameInfo: GameInfo;
  onComplete?: () => void;
}

export default function OpeningScene({ players, gameInfo, onComplete }: OpeningSceneProps) {
  const createdAt = new Date(gameInfo.created_at).toLocaleString("zh-CN");
  const firedRef = useRef(false);

  useEffect(() => {
    firedRef.current = false;
    const timer = setTimeout(() => {
      if (!firedRef.current) { firedRef.current = true; onComplete?.(); }
    }, players.length * 300 + 3000);
    return () => clearTimeout(timer);
  }, [players.length, onComplete]);

  return (
    <div className="h-full flex flex-col items-center justify-center px-6">
      <motion.div className="text-center mb-8" initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}>
        <h1 className="text-5xl font-bold text-white mb-2">
          {GAME_TITLES[gameInfo.type] ?? gameInfo.type}
        </h1>
        <p className="text-sm text-gray-500">{createdAt} · {players.length}人局</p>
      </motion.div>

      <motion.div className="grid grid-cols-2 lg:grid-cols-4 gap-4 max-w-3xl w-full"
        initial="hidden" animate="visible" variants={{ visible: { transition: { staggerChildren: 0.3 } } }}>
        {players.map((player) => (
          <motion.div key={player.id}
            className="bg-theater-surface border border-theater-border rounded-xl p-4 flex flex-col items-center text-center"
            variants={{ hidden: { opacity: 0, y: 20 }, visible: { opacity: 1, y: 0 } }}
            transition={{ duration: 0.4 }}>
            <PlayerAvatar name={player.name} playerId={player.id} size={52}
              word={player.word} role={player.role} />
            <p className="text-xs text-gray-500 mt-2 line-clamp-2">{player.persona}</p>
          </motion.div>
        ))}
      </motion.div>

      <motion.p className="text-gray-600 text-sm mt-6" initial={{ opacity: 0 }}
        animate={{ opacity: 1 }} transition={{ delay: players.length * 0.3 + 0.5 }}>
        游戏即将开始...
      </motion.p>
    </div>
  );
}
