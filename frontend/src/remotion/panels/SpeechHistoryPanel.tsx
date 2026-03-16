/**
 * Remotion speech history panel — simplified static list for video rendering.
 * No scrolling, no refs, no interactivity.
 */

import type { GameEvent, PlayerInfo } from "@/types/game-script";
import { getPlayerColor } from "@/utils/colors";

interface SpeechHistoryPanelProps {
  events: { event: GameEvent; round: number }[];
  players: PlayerInfo[];
}

export default function SpeechHistoryPanel({ events, players }: SpeechHistoryPanelProps) {
  const getName = (id: string) => players.find((p) => p.id === id)?.name ?? id;

  if (events.length === 0) {
    return (
      <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <span style={{ fontSize: 29, color: "#4b5563" }}>暂无发言</span>
      </div>
    );
  }

  // Show last N events that fit in the panel
  const maxVisible = 8;
  const visibleEvents = events.slice(-maxVisible);
  let lastRound = -1;

  return (
    <div style={{ padding: "21px 29px", display: "flex", flexDirection: "column", gap: 21 }}>
      {visibleEvents.map((item, idx) => {
        const showRoundHeader = item.round !== lastRound;
        lastRound = item.round;
        const content = item.event.action.payload["content"] ?? "";
        const isLastWords = item.event.action.type === "last_words";
        const color = getPlayerColor(item.event.player_id);
        const isCurrent = idx === visibleEvents.length - 1;

        return (
          <div key={idx}>
            {showRoundHeader && (
              <div style={{ fontSize: 26, color: "#4b5563", fontWeight: "bold", textAlign: "center", marginTop: idx > 0 ? 21 : 0, marginBottom: 10 }}>
                — 第 {item.round} 轮 —
              </div>
            )}
            <div style={{ opacity: isCurrent ? 1 : 0.7 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 10 }}>
                <span style={{ width: 23, height: 23, borderRadius: "50%", backgroundColor: color, flexShrink: 0 }} />
                <span style={{ fontSize: 29, fontWeight: 500, color: "#d1d5db" }}>
                  {getName(item.event.player_id)}
                </span>
                {isLastWords && <span style={{ fontSize: 26, color: "#6b7280" }}>遗言</span>}
              </div>
              <div style={{
                marginLeft: 39, borderRadius: "25px 25px 25px 5px",
                padding: "21px 29px", fontSize: 29, lineHeight: 1.5,
                backgroundColor: isCurrent ? `${color}20` : "rgba(255,255,255,0.05)",
                borderLeft: `4px solid ${isCurrent ? color : "transparent"}`,
                color: isCurrent ? "#e5e7eb" : "#9ca3af",
                // Limit text to 3 lines for compact display
                overflow: "hidden", display: "-webkit-box",
                WebkitLineClamp: 3, WebkitBoxOrient: "vertical",
              }}>
                {content}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
