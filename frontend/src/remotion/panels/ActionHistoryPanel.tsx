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

const ROLE_LABELS: Record<string, string> = {
  werewolf: "狼人",
  villager: "村民",
  seer: "预言家",
  witch: "女巫",
  hunter: "猎人",
  guard: "守卫",
  spy: "卧底",
  civilian: "平民",
  blank: "白板",
};

export default function ActionHistoryPanel({ events, players }: ActionHistoryPanelProps) {
  const getName = (id: string) => players.find((p) => p.id === id)?.name ?? id;
  const getRole = (id: string) => {
    const role = players.find((p) => p.id === id)?.role ?? "";
    return ROLE_LABELS[role] ?? "";
  };

  if (events.length === 0) {
    return (
      <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <span style={{ fontSize: 29, color: "#4b5563" }}>暂无行动</span>
      </div>
    );
  }

  const maxVisible = 10;
  const visibleEvents = events.slice(-maxVisible);
  let lastRound = -1;

  return (
    <div style={{ padding: "21px 29px", display: "flex", flexDirection: "column", gap: 16 }}>
      {visibleEvents.map((item, idx) => {
        const showRoundHeader = item.round !== lastRound;
        lastRound = item.round;
        const isCurrent = idx === visibleEvents.length - 1;
        const actionType = item.event.action.type;
        const payload = item.event.action.payload;
        const display = ACTION_DISPLAY[actionType] ?? { icon: "⚡", label: actionType };

        // Safely extract payload values — AI may return nested objects
        const safeStr = (v: unknown): string => {
          if (v == null) return "";
          if (typeof v === "string") return v;
          if (typeof v === "object") {
            const obj = v as Record<string, unknown>;
            return String(obj["use"] ?? obj["action"] ?? obj["content"] ?? obj["target"] ?? "");
          }
          return String(v);
        };
        const target = safeStr(payload["target"]) || safeStr(payload["target_player_id"]) || "";
        const rawUse = payload["use"];
        const witchUse = typeof rawUse === "object" && rawUse ? safeStr((rawUse as Record<string, unknown>)["use"] ?? rawUse) : safeStr(rawUse);
        const deaths = safeStr(payload["deaths"]);

        let mainText = "";
        if (actionType === "vote" || actionType === "wolf_kill" || actionType === "protect" || actionType === "seer_check" || actionType === "hunter_shoot") {
          mainText = `${display.label} → ${getName(target)}`;
        } else if (actionType === "witch_action") {
          mainText = WITCH_LABELS[witchUse] ?? witchUse;
          if (witchUse === "poison" && target) mainText += ` → ${getName(target)}`;
        } else if (actionType === "death_announce") {
          mainText = deaths ? deaths.split(",").map((n: string) => n.trim()).join("、") + " 死亡" : "死亡公告";
        } else if (actionType === "wolf_discuss") {
          mainText = display.label;
        }

        const playerName = item.event.player_id === "system" ? "" : getName(item.event.player_id);

        return (
          <div key={idx}>
            {showRoundHeader && (
              <div style={{ fontSize: 26, color: "#4b5563", fontWeight: "bold", textAlign: "center", marginTop: idx > 0 ? 21 : 0, marginBottom: 10 }}>
                — 第 {item.round} 轮 —
              </div>
            )}
            <div style={{
              borderRadius: 16, padding: "21px 29px",
              backgroundColor: isCurrent ? "rgba(255,255,255,0.1)" : "rgba(255,255,255,0.03)",
              border: isCurrent ? "1px solid rgba(255,255,255,0.1)" : "1px solid transparent",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                <span style={{ fontSize: 34 }}>{display.icon}</span>
                {playerName && (
                  <span style={{ fontSize: 29, fontWeight: 500, color: isCurrent ? "white" : "#9ca3af" }}>
                    {playerName}
                    {getRole(item.event.player_id) && (
                      <span style={{ fontSize: 20, color: "#6b7280", marginLeft: 6 }}>
                        ({getRole(item.event.player_id)})
                      </span>
                    )}
                  </span>
                )}
                <span style={{ fontSize: 29, color: isCurrent ? "#d1d5db" : "#6b7280" }}>
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
