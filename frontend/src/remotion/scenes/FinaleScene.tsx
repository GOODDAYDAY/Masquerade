/**
 * Remotion finale scene — identity reveal, winner, stats.
 */

import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import type { FinaleData } from "../timeline";
import PlayerAvatarStatic from "../components/PlayerAvatarStatic";
import FadeTransition from "../components/FadeTransition";

const WINNER_MAP: Record<string, { text: string; color: string }> = {
  civilian: { text: "平民阵营获胜", color: "#6366f1" },
  spy: { text: "卧底获胜", color: "#ef4444" },
  blank: { text: "白板获胜", color: "#d1d5db" },
  "spy,blank": { text: "非平民阵营获胜", color: "#ef4444" },
  village: { text: "好人阵营获胜", color: "#6366f1" },
  wolf: { text: "狼人阵营获胜", color: "#ef4444" },
};

function isWinnerRole(player: { role: string; extra?: Record<string, unknown> }, winner: string): boolean {
  if (winner === player.role) return true;
  const faction = (player.extra as Record<string, unknown>)?.faction;
  if (faction && faction === winner) return true;
  if (winner.includes(player.role)) return true;
  return false;
}

function getWinnerDisplay(winner: string): { text: string; color: string } {
  if (WINNER_MAP[winner]) return WINNER_MAP[winner];
  return { text: `${winner} 获胜`, color: "#d1d5db" };
}

interface FinaleSceneProps {
  data: FinaleData;
  durationInFrames: number;
}

export default function FinaleScene({ data, durationInFrames }: FinaleSceneProps) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { result, players } = data;
  const winnerInfo = getWinnerDisplay(result.winner);

  const durationSec = Math.round(result.total_duration_ms / 1000);
  const durationMin = Math.floor(durationSec / 60);
  const durationRemSec = durationSec % 60;

  // "Game Over" title - spring animation
  const titleScale = spring({ frame, fps, config: { damping: 10, stiffness: 80 } });
  const titleOpacity = interpolate(frame, [0, 18], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  // Player cards appear at frame 24 (~0.8s)
  const playersOpacity = interpolate(frame, [24, 39], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  // Winner text at frame 54 (~1.8s)
  const winnerOpacity = interpolate(frame, [54, 69], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const winnerScale = spring({ frame: Math.max(0, frame - 54), fps, config: { damping: 12, stiffness: 100 } });

  // Stats at frame 72 (~2.4s)
  const statsOpacity = interpolate(frame, [72, 84], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <FadeTransition durationInFrames={durationInFrames}>
      <div style={{ height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "0 57px" }}>
        {/* Title */}
        <h1 style={{
          fontSize: 114, fontWeight: "bold", color: "white",
          marginBottom: 75,
          opacity: titleOpacity,
          transform: `scale(${titleScale})`,
        }}>
          游戏结束
        </h1>

        {/* Player cards */}
        <div style={{
          display: "flex", gap: 44, justifyContent: "center", marginBottom: 75,
          flexWrap: "wrap", opacity: playersOpacity,
        }}>
          {players.map((p) => {
            const isWinner = isWinnerRole(p, result.winner);
            // Winner players get a subtle pulse effect
            const winnerPulse = isWinner && frame > 54
              ? 1 + 0.06 * Math.sin((frame - 54) * 0.15)
              : 1;
            return (
              <div key={p.id} style={{ transform: `scale(${winnerPulse})` }}>
                <PlayerAvatarStatic
                  name={p.name} playerId={p.id} size={130}
                  eliminated={result.eliminated_order.includes(p.id)}
                  word={p.word} role={p.role}
                />
              </div>
            );
          })}
        </div>

        {/* Winner */}
        <p style={{
          fontSize: 70, fontWeight: "bold",
          color: winnerInfo.color,
          marginBottom: 57,
          opacity: winnerOpacity,
          transform: `scale(${winnerScale})`,
        }}>
          {winnerInfo.text}
        </p>

        {/* Stats */}
        <div style={{
          display: "flex", gap: 114, textAlign: "center",
          opacity: statsOpacity,
        }}>
          <div>
            <p style={{ fontSize: 57, fontWeight: "bold", color: "white" }}>{result.total_rounds}</p>
            <p style={{ fontSize: 26, color: "#6b7280" }}>总轮次</p>
          </div>
          <div>
            <p style={{ fontSize: 57, fontWeight: "bold", color: "white" }}>{result.eliminated_order.length}</p>
            <p style={{ fontSize: 26, color: "#6b7280" }}>淘汰人数</p>
          </div>
          <div>
            <p style={{ fontSize: 57, fontWeight: "bold", color: "white" }}>
              {durationMin > 0 ? `${durationMin}m${durationRemSec}s` : `${durationSec}s`}
            </p>
            <p style={{ fontSize: 26, color: "#6b7280" }}>总耗时</p>
          </div>
        </div>
      </div>
    </FadeTransition>
  );
}
