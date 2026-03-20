# REQ-020: 游戏显示修复（女巫解药 + UI 布局）

| Field | Value |
|:---|:---|
| ID | REQ-020 |
| Status | Completed |
| Created | 2026-03-20 |
| Type | Bug Fix + UI Fix |

---

## 1. 问题描述

女巫使用解药（antidote）救人后，前端仍然显示被救玩家为死亡状态。

## 2. 根因分析

### 数据流

```
wolf_kill action → payload: {target: "玩家X"}     → 前端标记 X 死亡 ✓
witch_action     → payload: {use: "antidote"}     → 前端无法得知救了谁 ✗
death_announce   → payload: {deaths: ""}          → 后端正确（不含被救玩家）✓
```

### 断裂点

**`backend/engine/werewolf/game.py` 第 616-623 行**：女巫使用解药时，只设了布尔标志 `self.night_witch_save = True`，**没有把被救目标写入 action payload**。

```python
# 当前代码（有 bug）
if use == "antidote":
    self.night_witch_save = True
    self.witch_antidote_used = True
    # payload 仍为 {use: "antidote"}，无 target 字段
```

**`frontend/src/remotion/Video.tsx` 第 63-66 行**：前端尝试从 payload 读取 target 来取消死亡标记，但读不到。

```javascript
if (witchUse === "antidote") {
    const target = safeStr(payload["target"]);  // → undefined，因为后端没写入
    if (target) ids.delete(target);  // → 不执行
}
```

## 3. 修复方案

### 3.1 后端修复

在 `apply_action` 处理 `witch_action` 的 `antidote` 分支中，将被救目标写入 action payload：

```python
if use == "antidote":
    self.night_witch_save = True
    self.witch_antidote_used = True
    # 将被救目标写入 payload，供前端读取
    action.payload["target"] = self.night_wolf_target
```

### 3.2 前端验证

确认前端逻辑在 `target` 存在时能正确工作（现有代码已有 `ids.delete(target)` 逻辑，只需后端提供数据即可）。

---

## 4. UI 问题：头像换行 + 文字居中

### 4.1 头像应自适应一行显示

**现状**：avatar 容器使用 `flex-wrap`，当玩家多（如 12 人）时换行显示，视觉效果差。

**已有的缩放逻辑**：代码中已有 responsive 缩放（根据容器宽度缩小头像），但同时保留了 `flex-wrap` 兜底，导致某些情况仍会换行。

**修复**：移除 `flex-wrap`，让已有的 responsive 缩放逻辑完全接管。

涉及文件：
- `frontend/src/components/scenes/SpeakingScene.tsx` — `flex gap-3 justify-center mb-3 flex-wrap`
- `frontend/src/components/scenes/ActionScene.tsx` — 同上
- `frontend/src/components/scenes/VotingScene.tsx` — `flex gap-5 mb-8 flex-wrap justify-center`

### 4.2 发言文字居中显示

**现状**：发言气泡内文字左对齐（默认），用户希望居中。

**修复**：在发言气泡容器上加 `text-center`。

涉及文件：
- `frontend/src/components/scenes/SpeakingScene.tsx` — speech bubble
- `frontend/src/components/scenes/ActionScene.tsx` — action text bubble

---

## 5. 影响范围

| 改动 | 文件 | 改动量 |
|:---|:---|:---|
| 女巫解药 target | `backend/engine/werewolf/game.py` | +1 行 |
| 移除 flex-wrap | `SpeakingScene.tsx`, `ActionScene.tsx`, `VotingScene.tsx` | 各删 1 个 class |
| 文字居中 | `SpeakingScene.tsx`, `ActionScene.tsx` | 各加 1 个 class |

- **风险**：极低 — 全是 CSS class 级别的修改 + 一行 payload 赋值
