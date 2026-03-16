/**
 * Static player avatar — no framer-motion, safe for Remotion.
 * Mirrors the visual design of components/shared/PlayerAvatar.tsx.
 */

import { getPlayerColor } from "@/utils/colors";

interface PlayerAvatarStaticProps {
  name: string;
  playerId: string;
  size?: number;
  dimmed?: boolean;
  eliminated?: boolean;
  word?: string;
  role?: string;
}

// Role -> Chinese label
const ROLE_LABELS: Record<string, string> = {
  werewolf: "狼人",
  villager: "村民",
  seer: "预言家",
  witch: "女巫",
  hunter: "猎人",
  guard: "守卫",
};

// Role -> style for label display
const ROLE_STYLES: Record<string, { bg: string; text: string }> = {
  werewolf: { bg: "rgba(239,68,68,0.15)", text: "#ef4444" },
  villager: { bg: "rgba(99,102,241,0.15)", text: "#6366f1" },
  seer: { bg: "rgba(168,85,247,0.15)", text: "#c084fc" },
  witch: { bg: "rgba(34,197,94,0.15)", text: "#4ade80" },
  hunter: { bg: "rgba(249,115,22,0.15)", text: "#fb923c" },
  guard: { bg: "rgba(59,130,246,0.15)", text: "#60a5fa" },
};

export default function PlayerAvatarStatic({
  name, playerId, size = 156, dimmed = false, eliminated = false, word, role,
}: PlayerAvatarStaticProps) {
  const color = getPlayerColor(playerId);
  const initial = name.charAt(0);
  const isSpy = role === "spy";
  const isBlank = role === "blank";

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
      {/* Avatar circle */}
      <div
        style={{
          position: "relative",
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          borderRadius: "50%",
          width: size,
          height: size,
          backgroundColor: color,
          opacity: dimmed ? 0.3 : 1,
          filter: eliminated ? "grayscale(100%)" : "none",
        }}
      >
        <span style={{ fontWeight: "bold", color: "white", fontSize: size * 0.45, userSelect: "none" }}>
          {initial}
        </span>
        {/* Eliminated X marks */}
        {eliminated && (
          <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <div style={{ position: "absolute", width: "100%", height: 4, backgroundColor: "#ef4444", transform: "rotate(45deg)" }} />
            <div style={{ position: "absolute", width: "100%", height: 4, backgroundColor: "#ef4444", transform: "rotate(-45deg)" }} />
          </div>
        )}
        {/* Role badge */}
        {isSpy && !dimmed && (
          <span style={{
            position: "absolute", top: -10, right: -10,
            backgroundColor: "#ef4444", color: "white",
            fontSize: 18, fontWeight: "bold",
            padding: "0 10px", borderRadius: 9999, lineHeight: "31px",
          }}>
            卧底
          </span>
        )}
        {isBlank && !dimmed && (
          <span style={{
            position: "absolute", top: -10, right: -10,
            backgroundColor: "#6b7280", color: "white",
            fontSize: 18, fontWeight: "bold",
            padding: "0 10px", borderRadius: 9999, lineHeight: "31px",
          }}>
            白板
          </span>
        )}
      </div>
      {/* Name */}
      <span style={{
        fontSize: 26,
        color: dimmed ? "#4b5563" : "#d1d5db",
        textDecoration: eliminated ? "line-through" : "none",
      }}>
        {name}
      </span>
      {/* Word label (spy game) */}
      {!dimmed && word && (
        <span style={{
          fontSize: 23,
          padding: "5px 16px",
          borderRadius: 9,
          backgroundColor: isSpy ? "rgba(239,68,68,0.15)" : isBlank ? "rgba(107,114,128,0.15)" : "rgba(99,102,241,0.15)",
          color: isSpy ? "#ef4444" : isBlank ? "#9ca3af" : "#6366f1",
        }}>
          {word}
        </span>
      )}
      {/* Role label (werewolf game) */}
      {!word && role && ROLE_LABELS[role] && (
        <span style={{
          fontSize: 23,
          padding: "5px 16px",
          borderRadius: 9,
          backgroundColor: dimmed ? "rgba(107,114,128,0.1)" : (ROLE_STYLES[role]?.bg ?? "rgba(107,114,128,0.15)"),
          color: dimmed ? "#4b5563" : (ROLE_STYLES[role]?.text ?? "#9ca3af"),
        }}>
          {ROLE_LABELS[role]}
        </span>
      )}
    </div>
  );
}
