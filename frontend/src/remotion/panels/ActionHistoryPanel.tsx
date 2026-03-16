/**
 * Remotion action history panel — simplified static list for video rendering.
 */

import type { GameEvent, PlayerInfo } from "@/types/game-script";

interface ActionHistoryPanelProps {
  events: { event: GameEvent; round: number }[];
  players: PlayerInfo[];
}

const ACTION_DISPLAY: Record<string, { icon: string; label: string }> = {
  protect: { icon: "🛡️", label: "保护" },
  wolf_discuss: { icon: "🐺", label: "讨论" },
  wolf_kill: { icon: "🔪", label: "击杀" },
  witch_action: { icon: "🧪", label: "" },
  seer_check: { icon: "🔮", label: "查验" },
  hunter_shoot: { icon: "🔫", label: "开枪" },
  vote: { icon: "🗳️", label: "投票" },
  death_announce: { icon: "☠️", label: "死亡" },
  last_words: { icon: "💀", label: "遗言" },
};

const WITCH_LABELS: Record<string, string> = {
  antidote: "使用解药",
  poison: "使用毒药",
  skip: "不用药",
};

export default function ActionHistoryPanel({ events, players }: ActionHistoryPanelProps) {
  const getName = (id: string) => players.find((p) => p.id === id)?.name ?? id;

  if (events.length === 0) {
    return (
      <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <span style={{ fontSize: 22, color: "#4b5563" }}>暂无行动</span>
      </div>
    );
  }

  const maxVisible = 10;
  const visibleEvents = events.slice(-maxVisible);
  let lastRound = -1;

  return (
    <div style={{ padding: "16px 22px", display: "flex", flexDirection: "column", gap: 12 }}>
      {visibleEvents.map((item, idx) => {
        const showRoundHeader = item.round !== lastRound;
        lastRound = item.round;
        const isCurrent = idx === visibleEvents.length - 1;
        const actionType = item.event.action.type;
        const payload = item.event.action.payload;
        const display = ACTION_DISPLAY[actionType] ?? { icon: "⚡", label: actionType };

        const target = payload["target"] ?? payload["target_player_id"] ?? "";
        const witchUse = payload["use"] ?? "";
        const deaths = payload["deaths"] ?? "";

        let mainText = "";
        if (actionType === "vote" || actionType === "wolf_kill" || actionType === "protect" || actionType === "seer_check" || actionType === "hunter_shoot") {
          mainText = `${display.label} → ${getName(target)}`;
        } else if (actionType === "witch_action") {
          mainText = WITCH_LABELS[witchUse] ?? witchUse;
          if (witchUse === "poison" && target) mainText += ` → ${getName(target)}`;
        } else if (actionType === "death_announce") {
          mainText = deaths.split(",").map((n: string) => n.trim()).join("、") + " 死亡";
        } else if (actionType === "wolf_discuss") {
          mainText = display.label;
        }

        const playerName = item.event.player_id === "system" ? "" : getName(item.event.player_id);

        return (
          <div key={idx}>
            {showRoundHeader && (
              <div style={{ fontSize: 20, color: "#4b5563", fontWeight: "bold", textAlign: "center", marginTop: idx > 0 ? 16 : 0, marginBottom: 8 }}>
                — 第 {item.round} 轮 —
              </div>
            )}
            <div style={{
              borderRadius: 12, padding: "16px 22px",
              backgroundColor: isCurrent ? "rgba(255,255,255,0.1)" : "rgba(255,255,255,0.03)",
              border: isCurrent ? "1px solid rgba(255,255,255,0.1)" : "1px solid transparent",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <span style={{ fontSize: 26 }}>{display.icon}</span>
                {playerName && (
                  <span style={{ fontSize: 22, fontWeight: 500, color: isCurrent ? "white" : "#9ca3af" }}>
                    {playerName}
                  </span>
                )}
                <span style={{ fontSize: 22, color: isCurrent ? "#d1d5db" : "#6b7280" }}>
                  {mainText}
                </span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
