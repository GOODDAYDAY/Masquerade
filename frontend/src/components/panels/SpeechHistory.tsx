/**
 * Right panel — speech history list with chat bubble style.
 * Shows all speak/last_words events played so far, grouped by round.
 */

import { useEffect, useRef } from "react";
import type { GameEvent, PlayerInfo } from "@/types/game-script";

interface SpeechHistoryProps {
  events: { event: GameEvent; round: number }[];
  players: PlayerInfo[];
  currentEventIndex: number;
}

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

function getColor(playerId: string): string {
  return AVATAR_COLORS[hashCode(playerId) % AVATAR_COLORS.length]!;
}

export default function SpeechHistory({ events, players, currentEventIndex }: SpeechHistoryProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const getName = (id: string) => players.find((p) => p.id === id)?.name ?? id;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  if (events.length === 0) {
    return (
      <div className="h-full flex items-center justify-center">
        <span className="text-sm text-gray-600">暂无发言</span>
      </div>
    );
  }

  let lastRound = -1;

  return (
    <div className="h-full overflow-y-auto px-3 py-2 space-y-2">
      {events.map((item, idx) => {
        const showRoundHeader = item.round !== lastRound;
        lastRound = item.round;
        const isCurrent = idx === events.length - 1 && currentEventIndex >= 0;
        const content = item.event.action.payload["content"] ?? "";
        const isLastWords = item.event.action.type === "last_words";
        const color = getColor(item.event.player_id);

        return (
          <div key={idx}>
            {showRoundHeader && (
              <div className="text-xs text-gray-600 font-bold mt-3 mb-1 text-center">
                — 第 {item.round} 轮 —
              </div>
            )}
            {/* Chat bubble */}
            <div className={`transition-opacity ${isCurrent ? "opacity-100" : "opacity-70"}`}>
              {/* Player name */}
              <div className="flex items-center gap-1.5 mb-1">
                <span
                  className="w-2.5 h-2.5 rounded-full shrink-0"
                  style={{ backgroundColor: color }}
                />
                <span className="text-sm font-medium text-gray-300">
                  {getName(item.event.player_id)}
                </span>
                {isLastWords && (
                  <span className="text-xs text-gray-500">遗言</span>
                )}
              </div>
              {/* Bubble */}
              <div
                className="ml-4 rounded-xl rounded-tl-sm px-3 py-2 text-sm leading-relaxed"
                style={{
                  backgroundColor: isCurrent ? `${color}20` : "rgba(255,255,255,0.05)",
                  borderLeft: `2px solid ${isCurrent ? color : "transparent"}`,
                  color: isCurrent ? "#e5e7eb" : "#9ca3af",
                }}
              >
                {content}
              </div>
            </div>
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
