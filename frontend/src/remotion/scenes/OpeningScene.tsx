/**
 * Remotion opening scene — game title, player cards with staggered fade-in.
 */

import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import type { OpeningData } from "../timeline";
import PlayerAvatarStatic from "../components/PlayerAvatarStatic";
import FadeTransition from "../components/FadeTransition";

const GAME_TITLES: Record<string, string> = {
  spy: "谁是卧底",
  werewolf: "狼人杀",
};

interface OpeningSceneProps {
  data: OpeningData;
  durationInFrames: number;
}

export default function OpeningScene({ data, durationInFrames }: OpeningSceneProps) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { players, gameInfo } = data;
  const createdAt = new Date(gameInfo.created_at).toLocaleString("zh-CN");

  // Title spring animation
  const titleScale = spring({ frame, fps, config: { damping: 12, stiffness: 120 } });
  const titleOpacity = interpolate(frame, [0, 18], [0, 1], { extrapolateRight: "clamp" });

  // "Game starting" text appears after all player cards
  const startingTextFrame = players.length * 9 + 15;
  const startingOpacity = interpolate(
    frame,
    [startingTextFrame, startingTextFrame + 15],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  return (
    <FadeTransition durationInFrames={durationInFrames}>
      <div style={{
        height: "100%", display: "flex", flexDirection: "column",
        alignItems: "center", justifyContent: "center", padding: "0 57px",
      }}>
        {/* Title */}
        <div style={{
          textAlign: "center", marginBottom: 75,
          opacity: titleOpacity, transform: `scale(${titleScale})`,
        }}>
          <h1 style={{ fontSize: 114, fontWeight: "bold", color: "white", marginBottom: 21 }}>
            {GAME_TITLES[gameInfo.type] ?? gameInfo.type}
          </h1>
          <p style={{ fontSize: 31, color: "#6b7280" }}>
            {createdAt} · {players.length}人局
          </p>
        </div>

        {/* Player cards grid */}
        <div style={{
          display: "flex", flexWrap: "wrap", gap: 39,
          justifyContent: "center", maxWidth: 1690,
        }}>
          {players.map((player, i) => {
            // Each card fades in 9 frames apart (300ms at 30fps)
            const cardStartFrame = i * 9;
            const cardOpacity = interpolate(
              frame,
              [cardStartFrame, cardStartFrame + 12],
              [0, 1],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
            );
            const cardY = interpolate(
              frame,
              [cardStartFrame, cardStartFrame + 12],
              [26, 0],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
            );

            return (
              <div
                key={player.id}
                style={{
                  opacity: cardOpacity,
                  transform: `translateY(${cardY}px)`,
                  backgroundColor: "#14141f",
                  border: "1px solid #2a2a3a",
                  borderRadius: 25, padding: 39,
                  display: "flex", flexDirection: "column",
                  alignItems: "center", textAlign: "center",
                  width: 338,
                }}
              >
                <PlayerAvatarStatic
                  name={player.name}
                  playerId={player.id}
                  size={130}
                  word={player.word}
                  role={player.role}
                />
                <p style={{
                  fontSize: 26, color: "#6b7280", marginTop: 21,
                  overflow: "hidden", display: "-webkit-box",
                  WebkitLineClamp: 2, WebkitBoxOrient: "vertical",
                }}>
                  {player.persona}
                </p>
              </div>
            );
          })}
        </div>

        {/* "Game starting" text */}
        <p style={{ color: "#4b5563", fontSize: 31, marginTop: 57, opacity: startingOpacity }}>
          游戏即将开始...
        </p>
      </div>
    </FadeTransition>
  );
}
