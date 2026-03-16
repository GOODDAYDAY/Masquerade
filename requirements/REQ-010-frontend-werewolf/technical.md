# REQ-010 Technical Design

> Status: Completed
> Requirement: requirement.md
> Created: 2026-03-16
> Updated: 2026-03-16

## 1. Technology Stack

| Module | Technology | Rationale |
|:---|:---|:---|
| Scene Components | React + TypeScript + Tailwind | 现有技术栈，不引入新依赖 |
| Animation | Framer Motion (unchanged) | 已有依赖 |
| Timeline | Pure TypeScript (unchanged) | 无 React 依赖的逻辑层 |

## 2. Design Principles

- **数据驱动：** 组件根据 JSON 数据内容决定展示，不检查 game.type（除 Theater Header 外）
- **通用兜底：** 未知 action.type/phase/winner 不崩溃，显示原始值
- **最小改动：** 复用现有 SpeakingScene/VotingScene，新增 ActionScene 处理其余动作

## 3. Architecture Overview

改动文件清单：

| 文件 | 改动 |
|:---|:---|
| `frontend/src/types/game-script.ts` | phase 类型泛化为 string |
| `frontend/src/core/timeline.ts` | 场景构建逻辑重写，支持所有 action type |
| `frontend/src/components/Theater.tsx` | Header 按 game.type 区分 |
| `frontend/src/components/scenes/ActionScene.tsx` | **新增** — 通用动作场景 |
| `frontend/src/components/scenes/OpeningScene.tsx` | 标题/卡片按数据适配 |
| `frontend/src/components/scenes/FinaleScene.tsx` | winner 映射扩展 |
| `frontend/src/components/shared/RoundTitle.tsx` | phase 标签扩展 |

## 4. Module Design

### 4.1 Timeline 重构 (timeline.ts)

**核心变更：** 不再按 action.type 分组过滤，而是遍历 round.events 按原始顺序构建场景。

**新增场景类型：**

```typescript
export interface ActionScene {
  type: "action";
  event: GameEvent;
  round: number;
  eventIndex: number;
}

export type Scene = OpeningScene | RoundTitleScene | SpeakingScene | ActionScene | VotingScene | FinaleScene;
```

**构建逻辑：**

```typescript
for (const round of script.rounds) {
  // Round title — show at start of each round
  scenes.push({ type: "round-title", round: round.round_number, phase: "round-start" });

  let eventIndex = 0;
  for (const event of round.events) {
    const actionType = event.action.type;

    if (actionType === "speak" || actionType === "last_words") {
      scenes.push({ type: "speaking", event, round: round.round_number, eventIndex });
    } else if (actionType === "vote") {
      // Skip individual vote events — handled by VotingScene aggregate
    } else {
      // wolf_discuss, protect, wolf_kill, witch_action, seer_check, hunter_shoot, etc.
      scenes.push({ type: "action", event, round: round.round_number, eventIndex });
    }
    eventIndex++;
  }

  // Voting aggregate (if vote_result exists)
  if (round.vote_result) {
    const votingEvents = round.events.filter(e => e.action.type === "vote");
    scenes.push({ type: "voting", voteResult: round.vote_result, round: round.round_number, events: votingEvents });
  }
}
```

**Phase 标题：** 在每轮开始插入一个 round-title。Phase 标题不再硬编码 "speaking"/"voting"，而是用通用的 "round-start"。

**RoundTitleScene 修改：**

```typescript
export interface RoundTitleScene {
  type: "round-title";
  round: number;
  phase: string;  // was "speaking" | "voting"
}
```

**SCENE_DURATION 新增：**

```typescript
const SCENE_DURATION: Record<Scene["type"], number> = {
  opening: 8000,
  "round-title": 2500,
  speaking: 6000,
  action: 4000,    // NEW
  voting: 8000,
  finale: 10000,
};
```

### 4.2 ActionScene (新增组件)

**文件：** `frontend/src/components/scenes/ActionScene.tsx`

**职责：** 渲染所有非 speak/vote 的动作事件。

**动作类型标签映射：**

```typescript
const ACTION_LABELS: Record<string, string> = {
  protect: "🛡️ 守卫保护",
  wolf_discuss: "🐺 狼人讨论",
  wolf_kill: "🔪 狼人击杀",
  witch_action: "🧪 女巫用药",
  seer_check: "🔮 预言家查验",
  hunter_shoot: "🔫 猎人开枪",
  last_words: "💀 遗言",
};
// 兜底: 未知类型显示原始 action.type
```

**展示内容：**
- 玩家名 + 动作标签
- payload 内容（根据字段自动展示）：
  - `gesture` → 动作描述文本
  - `target` → "目标：玩家名"
  - `use` → "使用：解药/毒药/跳过"
  - `content` → 文本内容
- strategy_tip（如有，同 SpeakingScene 样式）

**视觉风格：**
- 夜晚（phase 以 `night_` 开头）：`bg-gray-900/80` 暗色调 + 🌙 标记
- 白天：正常 `bg-theater-surface`
- 无 TTS 播放（夜晚动作是手势/静默行动）

**场景时序：**
- 有文本内容（gesture/content）：打字机效果 + 基于文本长度的等待
- 无文本内容（纯 target）：固定 3 秒展示

### 4.3 Theater Header 改造

**文件：** `frontend/src/components/Theater.tsx`

**当前：** 硬编码 spy 词对展示

**改为：**

```typescript
function renderHeader(script: GameScript) {
  const gameType = script.game.type;

  if (gameType === "spy") {
    // 保留现有逻辑：平民词 vs 卧底词 vs 白板
    return <SpyHeader players={script.players} />;
  }

  // 通用 header：显示游戏类型 + 玩家数
  const gameLabels: Record<string, string> = {
    werewolf: "狼人杀",
    spy: "谁是卧底",
  };
  const label = gameLabels[gameType] ?? gameType;
  return <span className="text-gray-400">{label} · {script.players.length}人局</span>;
}
```

Spy 相关的变量（isAllBlank, civilianWord 等）移入条件分支内，不再污染通用代码。

### 4.4 FinaleScene 适配

**文件：** `frontend/src/components/scenes/FinaleScene.tsx`

**getWinnerDisplay 扩展：**

```typescript
const WINNER_MAP: Record<string, { text: string; colorClass: string }> = {
  civilian: { text: "平民阵营获胜", colorClass: "text-theater-accent" },
  spy: { text: "卧底获胜", colorClass: "text-theater-danger" },
  blank: { text: "白板获胜", colorClass: "text-gray-300" },
  "spy,blank": { text: "非平民阵营获胜", colorClass: "text-theater-danger" },
  village: { text: "好人阵营获胜", colorClass: "text-theater-accent" },
  wolf: { text: "狼人阵营获胜", colorClass: "text-theater-danger" },
};
// 兜底: 未知 winner 显示原始值
```

**角色动画：** 当前只对 spy/blank 做弹跳动画。改为通用逻辑：对 winner 阵营的角色做动画。

```typescript
// 根据 winner 和 player.role/extra.faction 判断是否为获胜方
const isWinner = (player: PlayerInfo, winner: string) => {
  if (winner === player.role) return true;
  if (player.extra?.faction === winner) return true;
  return false;
};
```

### 4.5 OpeningScene 适配

**文件：** `frontend/src/components/scenes/OpeningScene.tsx`

**标题：** 从硬编码"谁是卧底"改为根据 gameInfo.type 显示：

```typescript
const GAME_TITLES: Record<string, string> = {
  spy: "谁是卧底",
  werewolf: "狼人杀",
};
const title = GAME_TITLES[gameInfo.type] ?? gameInfo.type;
```

**玩家卡片：** PlayerAvatar 已经接受 word 和 role。对 werewolf 游戏：
- `word` 为空 → PlayerAvatar 不显示 word 标签（已有逻辑：`word || "无词"`，需改为空时隐藏）
- `role` 显示角色名
- `extra.faction` 可用于阵营色标（后续扩展）

### 4.6 RoundTitle 适配

**文件：** `frontend/src/components/shared/RoundTitle.tsx`

**phase 类型：** `"speaking" | "voting"` → `string`

**PHASE_LABELS 扩展：**

```typescript
const PHASE_LABELS: Record<string, string> = {
  "round-start": "开始",
  speaking: "发言阶段",
  voting: "投票阶段",
  night_guard: "守卫行动",
  night_wolf_discuss: "狼人讨论",
  night_wolf_kill: "狼人击杀",
  night_witch: "女巫行动",
  night_seer: "预言家查验",
  day_discussion: "白天讨论",
  day_voting: "白天投票",
};
// 兜底: PHASE_LABELS[phase] ?? phase
```

### 4.7 GameEvent 类型泛化

**文件：** `frontend/src/types/game-script.ts`

```typescript
// Before:
phase: "speaking" | "voting";

// After:
phase: string;
```

### 4.8 PlayerAvatar 小调整

**文件：** `frontend/src/components/shared/PlayerAvatar.tsx`

当前 word 为空时显示"无词"。对 werewolf 游戏不需要显示 word 区域。

修改：`word` 为空或 undefined 时不渲染 word 标签（而非显示"无词"）。

## 5. Data Model

无新增数据模型。仅 TypeScript 类型 `phase` 从联合类型改为 string。

## 6. API Design

无新增 API。

## 7. Key Flows

### 7.1 狼人杀 JSON 回放流程

```
JSON 加载 → buildSceneList()
  → Opening (标题"狼人杀", 玩家卡显示角色)
  → Round 1:
    → RoundTitle ("第1轮 开始")
    → ActionScene (protect, phase=night_guard, 🛡️ 守卫保护)
    → ActionScene (wolf_discuss × N, phase=night_wolf_discuss, 🐺 狼人讨论)
    → ActionScene (wolf_kill, phase=night_wolf_kill, 🔪 狼人击杀)
    → ActionScene (witch_action, phase=night_witch, 🧪 女巫用药)
    → ActionScene (seer_check, phase=night_seer, 🔮 预言家查验)
    → SpeakingScene (speak × N, 白天讨论)
    → VotingScene (投票结果聚合)
  → Round 2: ...
  → Finale (winner="wolf" → "狼人阵营获胜")
```

### 7.2 谁是卧底 JSON 回放流程（不变）

```
→ Opening (标题"谁是卧底", 显示词)
→ Round N: RoundTitle → SpeakingScene × N → VotingScene
→ Finale (winner="civilian" → "平民阵营获胜")
```

## 8. Shared Modules & Reuse Strategy

| 共享模块 | 使用者 |
|:---|:---|
| PlayerAvatar | OpeningScene, SpeakingScene, ActionScene, VotingScene, FinaleScene |
| AnimatedText | SpeakingScene (speech + tip), ActionScene (gesture text) |
| ExpressionIcon | SpeakingScene, ActionScene |
| RoundTitle | Timeline (all games) |
| ACTION_LABELS map | ActionScene (可扩展) |
| WINNER_MAP | FinaleScene (可扩展) |
| GAME_TITLES map | OpeningScene, Theater Header |

未来新增游戏只需：在 GAME_TITLES / WINNER_MAP / ACTION_LABELS 中添加条目。组件代码不需要修改。

## 9. Risks & Notes

| 风险 | 缓解 |
|:---|:---|
| ActionScene 对所有动作用同一布局 | 通过 payload 字段自动适配展示内容，暂不做专用组件 |
| 夜晚动作太多导致回放冗长 | ActionScene 固定 4 秒，比 SpeakingScene 的 6 秒短 |
| 旧 spy JSON 无 strategy_tip 字段 | ActionScene 判空不展示（已有逻辑） |

## 10. Change Log

| Version | Date | Changes | Affected Scope | Reason |
|:---|:---|:---|:---|:---|
| v1 | 2026-03-16 | Initial version | ALL | - |
