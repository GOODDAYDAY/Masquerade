/**
 * Player avatar — initial-based circle with color, optional word/role label.
 */

import { motion } from "framer-motion";

interface PlayerAvatarProps {
  name: string;
  playerId: string;
  size?: number;
  dimmed?: boolean;
  eliminated?: boolean;
  /** Show word below avatar */
  word?: string;
  /** Show role badge (e.g. "spy") */
  role?: string;
}

// Role → Chinese label (for games without words, like werewolf)
const ROLE_LABELS: Record<string, string> = {
  werewolf: "狼人",
  villager: "村民",
  seer: "预言家",
  witch: "女巫",
  hunter: "猎人",
  guard: "守卫",
};

// Role → style for label display
const ROLE_STYLES: Record<string, string> = {
  werewolf: "bg-theater-danger/15 text-theater-danger",
  villager: "bg-theater-accent/15 text-theater-accent",
  seer: "bg-purple-500/15 text-purple-400",
  witch: "bg-green-500/15 text-green-400",
  hunter: "bg-orange-500/15 text-orange-400",
  guard: "bg-blue-500/15 text-blue-400",
};

const AVATAR_COLORS = [
  "#6366f1", "#ec4899", "#14b8a6", "#f59e0b",
  "#8b5cf6", "#ef4444", "#06b6d4", "#10b981",
];

function hashCode(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

export default function PlayerAvatar({
  name, playerId, size = 64, dimmed = false, eliminated = false, word, role,
}: PlayerAvatarProps) {
  const color = AVATAR_COLORS[hashCode(playerId) % AVATAR_COLORS.length]!;
  const initial = name.charAt(0);
  const isSpy = role === "spy";
  const isBlank = role === "blank";

  return (
    <div className="flex flex-col items-center gap-1">
      <motion.div
        className="relative inline-flex items-center justify-center rounded-full"
        style={{
          width: size, height: size, backgroundColor: color,
          opacity: dimmed ? 0.3 : 1,
          filter: eliminated ? "grayscale(100%)" : "none",
        }}
        animate={{ opacity: dimmed ? 0.3 : 1 }}
        transition={{ duration: 0.3 }}
      >
        <span className="font-bold text-white select-none" style={{ fontSize: size * 0.45 }}>
          {initial}
        </span>
        {eliminated && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-full h-0.5 bg-red-500 rotate-45 absolute" />
            <div className="w-full h-0.5 bg-red-500 -rotate-45 absolute" />
          </div>
        )}
        {/* Role badge */}
        {isSpy && !dimmed && (
          <span className="absolute -top-1 -right-1 bg-theater-danger text-white text-[8px] font-bold px-1 rounded-full leading-tight">
            卧底
          </span>
        )}
        {isBlank && !dimmed && (
          <span className="absolute -top-1 -right-1 bg-gray-500 text-white text-[8px] font-bold px-1 rounded-full leading-tight">
            白板
          </span>
        )}
      </motion.div>
      {/* Name */}
      <span className={`text-xs ${dimmed ? "text-gray-600" : "text-gray-300"} ${eliminated ? "line-through text-gray-600" : ""}`}>
        {name}
      </span>
      {/* Word label (spy game) or role label (werewolf game) */}
      {!dimmed && word && (
        <span className={`text-[10px] px-1.5 py-0.5 rounded ${
          isSpy ? "bg-theater-danger/15 text-theater-danger"
          : isBlank ? "bg-gray-500/15 text-gray-400"
          : "bg-theater-accent/15 text-theater-accent"
        }`}>
          {word}
        </span>
      )}
      {!word && role && ROLE_LABELS[role] && (
        <span className={`text-[10px] px-1.5 py-0.5 rounded ${
          dimmed ? "bg-gray-500/10 text-gray-600" : (ROLE_STYLES[role] ?? "bg-gray-500/15 text-gray-400")
        }`}>
          {ROLE_LABELS[role]}
        </span>
      )}
    </div>
  );
}
