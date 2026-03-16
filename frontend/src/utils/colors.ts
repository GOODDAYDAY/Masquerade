/**
 * Shared color utilities for player avatars.
 * Used by both interactive Theater and Remotion video rendering.
 */

export const AVATAR_COLORS = [
  "#6366f1", "#ec4899", "#14b8a6", "#f59e0b",
  "#8b5cf6", "#ef4444", "#06b6d4", "#10b981",
];

export function hashCode(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

export function getPlayerColor(playerId: string): string {
  return AVATAR_COLORS[hashCode(playerId) % AVATAR_COLORS.length]!;
}
