/**
 * Remotion voting scene — progressive vote reveal + result.
 * Vote[i] revealed at frame >= i * 36 (1.2s intervals at 30fps).
 */

import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import type { GameScript } from "@/types/game-script";
import type { VotingData } from "../timeline";
import PlayerAvatarStatic from "../components/PlayerAvatarStatic";
import FadeTransition from "../components/FadeTransition";
import { msToFrames } from "../timeline";

interface VotingSceneProps {
  data: VotingData;
  durationInFrames: number;
  script: GameScript;
  eliminatedIds: string[];
}

export default function VotingScene({
  data, durationInFrames, script, eliminatedIds,
}: VotingSceneProps) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { voteResult, voterOrder } = data;
  const players = script.players;

  const voteIntervalFrames = msToFrames(1200, fps); // 36 frames at 30fps
  const allVotesRevealedFrame = voterOrder.length * voteIntervalFrames;
  const resultFrame = allVotesRevealedFrame + msToFrames(1000, fps);

  // How many votes are revealed at the current frame
  const revealedCount = Math.min(
    voterOrder.length,
    Math.floor(frame / voteIntervalFrames) + 1,
  );
  const revealedVoters = voterOrder.slice(0, revealedCount);
  const showResult = frame >= resultFrame;

  // Tally votes for badge display
  const tally: Record<string, number> = {};
  for (const voter of revealedVoters) {
    const target = voteResult.votes[voter]!;
    tally[target] = (tally[target] ?? 0) + 1;
  }

  const getName = (id: string) => players.find((p) => p.id === id)?.name ?? id;

  // Players who were already eliminated before this vote
  const previouslyEliminated = eliminatedIds.filter((id) => id !== voteResult.eliminated);

  // Result animation
  const resultScale = showResult
    ? spring({ frame: frame - resultFrame, fps, config: { damping: 10, stiffness: 100 } })
    : 0;
  const resultOpacity = showResult
    ? interpolate(frame, [resultFrame, resultFrame + 15], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })
    : 0;

  return (
    <FadeTransition durationInFrames={durationInFrames}>
      <div style={{ height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "0 44px" }}>
        {/* Player row with vote count badges */}
        <div style={{ display: "flex", gap: 34, marginBottom: 58, flexWrap: "wrap", justifyContent: "center" }}>
          {players.map((p) => {
            const isOut = previouslyEliminated.includes(p.id) || (showResult && voteResult.eliminated === p.id);
            const votes = tally[p.id] ?? 0;
            return (
              <div key={p.id} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
                <PlayerAvatarStatic
                  name={p.name} playerId={p.id} size={80}
                  eliminated={isOut} word={p.word} role={p.role}
                />
                {votes > 0 && (
                  <span style={{
                    backgroundColor: "#6366f1", color: "white",
                    fontSize: 20, fontWeight: "bold",
                    padding: "4px 16px", borderRadius: 9999,
                  }}>
                    {votes} 票
                  </span>
                )}
              </div>
            );
          })}
        </div>

        {/* Vote list */}
        <div style={{ maxWidth: 700, width: "100%", display: "flex", flexDirection: "column", gap: 16, marginBottom: 44 }}>
          {revealedVoters.map((voter, i) => {
            const entryFrame = i * voteIntervalFrames;
            const entryOpacity = interpolate(
              frame, [entryFrame, entryFrame + 9], [0, 1],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
            );
            const entryX = interpolate(
              frame, [entryFrame, entryFrame + 9], [-15, 0],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
            );
            return (
              <div key={voter} style={{
                opacity: entryOpacity,
                transform: `translateX(${entryX}px)`,
                display: "flex", alignItems: "center", gap: 18,
                backgroundColor: "#14141f", border: "1px solid #2a2a3a",
                borderRadius: 12, padding: "16px 22px",
              }}>
                <span style={{ fontSize: 24, color: "#d1d5db", flex: 1 }}>{getName(voter)}</span>
                <span style={{ fontSize: 20, color: "#4b5563" }}>→</span>
                <span style={{ fontSize: 24, color: "#6366f1", fontWeight: 500 }}>{getName(voteResult.votes[voter]!)}</span>
              </div>
            );
          })}
        </div>

        {/* Voting in progress indicator */}
        {revealedCount < voterOrder.length && (
          <p style={{
            fontSize: 24, color: "#4b5563",
            opacity: interpolate(frame % 45, [0, 15, 30, 45], [0.3, 1, 0.3, 0.3]),
          }}>
            投票中...
          </p>
        )}

        {/* Result */}
        {showResult && (
          <div style={{
            textAlign: "center", marginTop: 16,
            opacity: resultOpacity,
            transform: `scale(${resultScale})`,
          }}>
            {voteResult.eliminated ? (
              <p style={{ fontSize: 44, fontWeight: "bold", color: "#ef4444" }}>
                {getName(voteResult.eliminated)} 被淘汰
              </p>
            ) : (
              <p style={{ fontSize: 44, fontWeight: "bold", color: "#f59e0b" }}>
                平票 — 无人淘汰
              </p>
            )}
          </div>
        )}
      </div>
    </FadeTransition>
  );
}
