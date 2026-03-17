/**
 * Left panel — action history list with card style.
 * Shows all non-speak events played so far, grouped by round.
 */

import { useEffect, useRef } from "react";
import type { GameEvent, PlayerInfo } from "@/types/game-script";

interface ActionHistoryProps {
  events: { event: GameEvent; round: number }[];
  players: PlayerInfo[];
  currentEventIndex: number;
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

export default function ActionHistory({ events, players, currentEventIndex }: ActionHistoryProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const getName = (id: string) => players.find((p) => p.id === id)?.name ?? id;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  if (events.length === 0) {
    return (
      <div className="h-full flex items-center justify-center">
        <span className="text-sm text-gray-600">暂无行动</span>
      </div>
    );
  }

  let lastRound = -1;

  return (
    <div className="h-full overflow-y-auto px-3 py-2 space-y-1.5">
      {events.map((item, idx) => {
        const showRoundHeader = item.round !== lastRound;
        lastRound = item.round;
        const isCurrent = idx === events.length - 1 && currentEventIndex >= 0;
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
        const gesture = safeStr(payload["gesture"]);

        let mainText = "";
        let subText = "";

        if (actionType === "vote" || actionType === "wolf_kill" || actionType === "protect" || actionType === "seer_check" || actionType === "hunter_shoot") {
          mainText = `${display.label} → ${getName(target)}`;
        } else if (actionType === "witch_action") {
          mainText = WITCH_LABELS[witchUse] ?? witchUse;
          if (witchUse === "poison" && target) {
            mainText += ` → ${getName(target)}`;
          }
        } else if (actionType === "death_announce") {
          mainText = deaths.split(",").map((n: string) => n.trim()).join("、") + " 死亡";
        } else if (actionType === "wolf_discuss") {
          mainText = display.label;
          subText = gesture;
        }

        const playerName = item.event.player_id === "system" ? "" : getName(item.event.player_id);

        return (
          <div key={idx}>
            {showRoundHeader && (
              <div className="text-xs text-gray-600 font-bold mt-3 mb-1 text-center">
                — 第 {item.round} 轮 —
              </div>
            )}
            {/* Action card */}
            <div className={`rounded-lg px-3 py-2 transition-colors ${
              isCurrent
                ? "bg-white/10 border border-white/10"
                : "bg-white/[0.03] border border-transparent"
            }`}>
              <div className="flex items-center gap-1.5">
                <span className="text-base">{display.icon}</span>
                {playerName && (
                  <span className={`text-sm font-medium ${isCurrent ? "text-white" : "text-gray-400"}`}>
                    {playerName}
                  </span>
                )}
                <span className={`text-sm ${isCurrent ? "text-gray-300" : "text-gray-500"}`}>
                  {mainText}
                </span>
              </div>
              {subText && (
                <p className={`mt-1 text-sm leading-relaxed pl-6 ${isCurrent ? "text-gray-400 italic" : "text-gray-600 italic"}`}>
                  {subText}
                </p>
              )}
            </div>
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
