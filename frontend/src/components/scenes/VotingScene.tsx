/**
 * F-04: Voting phase — vote reveal with player words always visible.
 */

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { GameEvent, PlayerInfo, VoteResult } from "@/types/game-script";
import PlayerAvatar from "@/components/shared/PlayerAvatar";
import { useTheater } from "@/components/Theater";

interface VotingSceneProps {
  voteResult: VoteResult;
  events: GameEvent[];
  players: PlayerInfo[];
  onComplete?: () => void;
}

export default function VotingScene({ voteResult, players, onComplete }: VotingSceneProps) {
  const { speed, eliminatedIds } = useTheater();
  const [revealedVotes, setRevealedVotes] = useState<string[]>([]);
  const [showResult, setShowResult] = useState(false);

  const voters = Object.keys(voteResult.votes);

  useEffect(() => {
    if (revealedVotes.length < voters.length) {
      const timer = setTimeout(() => {
        const next = voters[revealedVotes.length];
        if (next) setRevealedVotes((prev) => [...prev, next]);
      }, 1200 / speed);
      return () => clearTimeout(timer);
    }
    const timer = setTimeout(() => setShowResult(true), 1000 / speed);
    return () => clearTimeout(timer);
  }, [revealedVotes, voters, speed]);

  useEffect(() => {
    if (showResult) {
      const timer = setTimeout(() => onComplete?.(), 2500 / speed);
      return () => clearTimeout(timer);
    }
  }, [showResult, onComplete, speed]);

  const tally: Record<string, number> = {};
  for (const voter of revealedVotes) {
    const target = voteResult.votes[voter]!;
    tally[target] = (tally[target] ?? 0) + 1;
  }

  const getName = (id: string) => players.find((p) => p.id === id)?.name ?? id;

  // Players who were already eliminated before this vote
  const previouslyEliminated = eliminatedIds.filter((id) => id !== voteResult.eliminated);

  return (
    <div className="h-full flex flex-col items-center justify-center px-6">
      {/* Player row with words + vote count */}
      <div className="flex gap-5 mb-8 justify-center">
        {players.map((p) => {
          const isOut = previouslyEliminated.includes(p.id) || (showResult && voteResult.eliminated === p.id);
          return (
            <div key={p.id} className="flex flex-col items-center gap-1">
              <PlayerAvatar name={p.name} playerId={p.id} size={44}
                eliminated={isOut} word={p.word} role={p.role} />
              {(tally[p.id] ?? 0) > 0 && (
                <motion.span className="bg-theater-accent text-white text-[11px] font-bold px-2 py-0.5 rounded-full"
                  initial={{ scale: 0 }} animate={{ scale: 1 }} key={tally[p.id]}>
                  {tally[p.id]} 票
                </motion.span>
              )}
            </div>
          );
        })}
      </div>

      {/* Vote list */}
      <div className="space-y-2 mb-6 max-w-sm w-full">
        <AnimatePresence>
          {revealedVotes.map((voter) => (
            <motion.div key={voter}
              className="flex items-center gap-2.5 bg-theater-surface border border-theater-border rounded-lg px-3 py-2"
              initial={{ opacity: 0, x: -15 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.3 }}>
              <span className="text-sm text-gray-300 flex-1">{getName(voter)}</span>
              <span className="text-gray-600 text-xs">→</span>
              <span className="text-sm text-theater-accent font-medium">{getName(voteResult.votes[voter]!)}</span>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {revealedVotes.length < voters.length && (
        <motion.p className="text-gray-600 text-sm" animate={{ opacity: [0.3, 1, 0.3] }}
          transition={{ repeat: Infinity, duration: 1.5 }}>投票中...</motion.p>
      )}

      {showResult && (
        <motion.div className="text-center mt-2" initial={{ opacity: 0, scale: 0.85 }}
          animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.5 }}>
          {voteResult.eliminated ? (
            <p className="text-2xl font-bold text-theater-danger">{getName(voteResult.eliminated)} 被淘汰</p>
          ) : (
            <p className="text-2xl font-bold text-theater-gold">平票 — 无人淘汰</p>
          )}
        </motion.div>
      )}
    </div>
  );
}
