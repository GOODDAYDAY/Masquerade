# REQ-017: UI Layout Fix & AI Intelligence Upgrade — Technical Design

## 1. Overview

本需求分两个独立部分：(A) 前端 UI 修复，(B) 后端 AI Prompt 升级。两部分无交叉依赖，可并行开发。

## 2. File Change Map

| 文件 | Part | 改动 |
|:---|:---|:---|
| `backend/engine/shared_prompts.py` | B | 新增 WEREWOLF_META_KNOWLEDGE, ANTI_ECHO_RULES, PERSONA_DEPTH_RULES, CROSS_ROUND_VARIATION |
| `backend/engine/werewolf/strategy.py` | B | 所有 DAY_THINKER 注入新规则；WOLF_DAY_THINKER 加话术分化；WOLF_DAY_OPTIMIZER 加遗言策略；所有 DAY_EVALUATOR 加反回声扣分；所有 DAY_OPTIMIZER 加跨轮变化 |
| `frontend/src/remotion/scenes/SpeakingScene.tsx` | A | 头像自适应 + 字幕自动滚动 |
| `frontend/src/remotion/scenes/ActionScene.tsx` | A | 头像自适应 |
| `frontend/src/remotion/scenes/OpeningScene.tsx` | A | 头像自适应 |
| `frontend/src/remotion/components/AnimatedText.tsx` | A | 新增溢出回调 |
| `frontend/src/components/scenes/SpeakingScene.tsx` | A | 头像自适应 + 字幕滚动 (CSS) |
| `frontend/src/components/scenes/ActionScene.tsx` | A | 头像自适应 |

## 3. Part A: UI Layout Fix

### 3.1 头像自适应算法

**核心思路**：根据玩家人数动态计算头像大小，保证一行放下。

```typescript
function getAvatarSize(playerCount: number, defaults: { active: number, inactive: number }, maxRowWidth: number, gap: number) {
  // 最坏情况：所有头像按 inactive 大小 + 1 个 active 放大 1.1x
  const totalGap = (playerCount - 1) * gap;
  const availableWidth = maxRowWidth - totalGap;
  const maxInactiveSize = availableWidth / playerCount;

  if (maxInactiveSize >= defaults.inactive) {
    return defaults; // 放得下，不缩
  }

  // 缩放比例
  const scale = maxInactiveSize / defaults.inactive;
  return {
    inactive: Math.floor(defaults.inactive * scale),
    active: Math.floor(defaults.active * scale),
  };
}
```

**Remotion 参数**（2560x1440 画面）：
- SpeakingScene/ActionScene: `maxRowWidth = 2560 - 57*2 = 2446`, `gap = 29`, defaults `{ active: 156, inactive: 130 }`
- OpeningScene: `maxRowWidth = 1690`, `gap = 29`, defaults `{ active: 104, inactive: 104 }`
- VotingScene: 已用 104px + 44px gap，12 人 = 104*12 + 44*11 = 1732px，不需改

**Theater 参数**：
- 容器宽度动态获取（`useRef` + `ResizeObserver` 或 CSS `container query`）
- defaults `{ active: 64, inactive: 52 }`

**实现位置**：不抽公共模块，各场景内联计算（计算量极小）。

### 3.2 字幕帧驱动自动滚动（Remotion）

**问题**：`AnimatedText` 逐字打出文本，当文本超出 `maxHeight: 500` 时被 `overflow: hidden` 裁切。

**方案**：给 speech bubble 容器增加帧驱动的 `translateY` 偏移。

**实现细节**：

1. `AnimatedText` 增加 `onOverflow` 回调或直接在 `SpeakingScene` 中计算：
   - 已显示字符数 → 估算已渲染文本高度（基于 fontSize、lineHeight、容器宽度）
   - 当估算高度 > maxHeight 时，计算需要上移的偏移量

2. 更简洁的方案——**基于文本行数估算**：

```typescript
// 估算当前可见文本的渲染高度
const visibleChars = Math.floor(((frame - startFrame) / fps) * charsPerSecond);
const visibleText = text.slice(0, visibleChars);
const charsPerLine = Math.floor(bubbleWidth / fontSize);  // 约 26 chars per line @ 50px in 1300px
const lineCount = Math.ceil(visibleText.length / charsPerLine);
const textHeight = lineCount * fontSize * lineHeight;  // lineHeight = 1.5
const maxVisible = 500;  // maxHeight of bubble

const scrollOffset = textHeight > maxVisible
  ? -(textHeight - maxVisible)
  : 0;
```

3. 在 speech bubble 内部添加一个 wrapper div，应用 `translateY(scrollOffset)`：

```tsx
<div style={{ maxHeight: 500, overflow: "hidden" }}>
  <div style={{ transform: `translateY(${scrollOffset}px)`, transition: "none" }}>
    <AnimatedText ... />
  </div>
</div>
```

4. **滚动后停留**：文字全部打完后不立即切场景。timeline.ts 的 speaking 场景时长计算已包含 `+800ms` 尾部缓冲，足够。

### 3.3 字幕滚动（Theater 交互式）

更简单——直接改 CSS：
- speech bubble: `overflow-y: auto` 替代无 overflow 限制
- `AnimatedText` 组件的容器加 `ref`，每次文字更新时 `scrollTo({ top: el.scrollHeight, behavior: "smooth" })`

## 4. Part B: AI Intelligence Upgrade

### 4.1 新增共享 Prompt 片段

在 `shared_prompts.py` 中新增 4 个常量：

#### WEREWOLF_META_KNOWLEDGE

```python
WEREWOLF_META_KNOWLEDGE = """
**【狼人杀元知识——所有玩家的游戏常识】**
1. 预言家验谁完全是策略自由，查验顺序不构成任何怀疑依据。"查验顺序可疑"是无效论证，不要使用也不要被这种论证说服。
2. 首夜验人可以基于直觉或随机，不需要特殊理由。
3. 好人遗言应传递关键信息（查验结果、怀疑目标等）；狼人遗言应继续伪装，绝对不能承认狼人身份。
4. "平安夜"（无人死亡的夜晚）是重要线索——可能是守卫守中、女巫救人、或狼人空刀，必须深入分析原因和影响。
5. 投票记录比发言更可靠——谁投了谁，是最重要的行为证据。说一套做一套的人高度可疑。
6. 不要纠缠于谁"态度好""态度差"，关注逻辑一致性和信息链条。态度可以伪装，逻辑链无法伪装。
"""
```

#### ANTI_ECHO_RULES

```python
ANTI_ECHO_RULES = """
**【反回声规则（强制）】**
- 认真听取前面所有人的发言，但你的发言必须提出【新观点】【新分析角度】或【新证据链】
- 如果某个证据或论点前面的发言者已经充分讨论过，你最多一句话带过（"同意xxx关于yyy的分析"），然后必须提出你自己的独到见解
- 绝对禁止大段复述前人已说过的话或引用前人已引用过的原话
- 如果你确实没有全新的观点，至少从不同角度解读已有信息，或指出前人分析中的漏洞
"""
```

#### PERSONA_DEPTH_RULES（注入所有 DAY_OPTIMIZER）

```python
PERSONA_DEPTH_RULES = """
**【人设表达规则】**
- 人设通过你的【推理方式】和【关注点】来体现，而不是口头禅或固定开场白
- 禁止连续两轮使用相同的开场白、结尾语或标志性台词
- 冲动型人设 → 快速下结论、容易被反驳后改变立场，而非每次都说"你凭什么"
- 深沉型人设 → 从细节切入、后发制人，而非每次都说"有意思"
- 话痨型人设 → 信息量大、关联多条线索，而非每次都说"终于轮到我了"
- 犹豫型人设 → 先列出正反两面再艰难选择，而非反复说"我不确定"
"""
```

#### NEW_INFO_PRIORITY（注入所有 DAY_THINKER）

```python
NEW_INFO_PRIORITY = """
**【信息新鲜度规则】**
- 优先讨论本轮的新信息：谁昨晚死了？为什么？这对局势有什么影响？
- 如果昨晚是平安夜，必须深入分析原因（守卫守中？女巫救人？狼人空刀？）并讨论对局势的影响
- 回顾历史信息时，只引用尚未被充分讨论的旧信息，不要翻炒已经讨论透彻的证据
"""
```

### 4.2 修改注入点

#### 4.2.1 所有 DAY_THINKER（6 个角色）

在每个 DAY_THINKER 的 `.format()` 中追加 `WEREWOLF_META_KNOWLEDGE`、`ANTI_ECHO_RULES`、`NEW_INFO_PRIORITY`。

具体方式——以 VILLAGER_DAY_THINKER 为例：

```python
VILLAGER_DAY_THINKER = """你是...
{anti_name_bias}
{meta_knowledge}
{anti_echo}
{new_info_priority}

你没有特殊能力...
...
""".format(
    anti_name_bias=ANTI_NAME_BIAS,
    meta_knowledge=WEREWOLF_META_KNOWLEDGE,
    anti_echo=ANTI_ECHO_RULES,
    new_info_priority=NEW_INFO_PRIORITY,
    voting_evidence_rules=VOTING_EVIDENCE_RULES,
)
```

同理注入到：`WOLF_DAY_THINKER`, `SEER_DAY_THINKER`, `WITCH_DAY_THINKER`, `GUARD_DAY_THINKER`, `HUNTER_DAY_THINKER`（通过 HUNTER_NORMAL_CONTEXT / HUNTER_SHOOT_CONTEXT）。

#### 4.2.2 WOLF_DAY_THINKER 追加话术分化

在 WOLF_DAY_THINKER 的"深度伪装策略"部分追加第 6 条：

```
6. **话术分化（铁律）：** 你知道谁是你的狼人队友。白天发言时，你和队友必须采用完全不同的叙事角度：
   - 不要引用或附和队友的论点。如果队友攻击了某人，你另辟蹊径或保持中立
   - 如果队友的论点被质疑，不要急于辩护——这会暴露狼人关联
   - 策略分工：一狼主攻（引导方向）、一狼潜水（少说装好人）、一狼搅局（制造混乱）、一狼跟风（跟好人节奏）
```

#### 4.2.3 WOLF_DAY_OPTIMIZER 追加遗言策略

将现有第 3 条遗言规则：
```
3. 如果是遗言（last_words）：简短有力，可以适当暴露信息。
```
改为：
```
3. 如果是遗言（last_words）：
   - 好人遗言：简短有力，传递关键信息
   - 狼人遗言铁律：永远不要承认狼人身份。即使全场已经确认你是狼，遗言也要坚持"我是好人"。目标是给存活的队友制造生存空间——反咬一个好人、质疑投你的人的逻辑、或制造混乱。
```

#### 4.2.4 所有 DAY_EVALUATOR 追加反回声扣分

在所有 DAY_EVALUATOR 的评估标准中追加：
```
N. **回声检查（-3分）：** 如果发言内容与本轮前面发言者高度重复（引用相同的原话、提出相同的论点、使用相同的论证结构），扣3分。
```

影响：VILLAGER_DAY_EVALUATOR（也被 Guard、Witch 复用）、WOLF_DAY_EVALUATOR、SEER_DAY_EVALUATOR、HUNTER_DAY_EVALUATOR。

#### 4.2.5 所有 DAY_OPTIMIZER 追加跨轮变化 + 人设深度

在所有 DAY_OPTIMIZER 中追加 `PERSONA_DEPTH_RULES` 和跨轮变化规则：

```
{persona_depth}

**【跨轮变化规则】**
- 你前几轮的发言已在上下文中。本轮发言的开场方式、句式、论证角度必须与前几轮明显不同。
- 如果前轮以提问开头，这轮换成陈述；如果前轮激动，这轮冷静分析。
```

影响：VILLAGER_DAY_OPTIMIZER（被 Guard、Witch 复用）、WOLF_DAY_OPTIMIZER、SEER_DAY_OPTIMIZER、HUNTER_DAY_OPTIMIZER。

### 4.3 Token 预算分析

每个新增 prompt 片段的中文字符数：
- WEREWOLF_META_KNOWLEDGE: ~200 字 ≈ 130 tokens
- ANTI_ECHO_RULES: ~120 字 ≈ 80 tokens
- NEW_INFO_PRIORITY: ~100 字 ≈ 65 tokens
- PERSONA_DEPTH_RULES: ~180 字 ≈ 120 tokens
- Wolf 话术分化: ~150 字 ≈ 100 tokens
- Wolf 遗言策略: ~100 字 ≈ 65 tokens
- 跨轮变化: ~80 字 ≈ 55 tokens

**Thinker 新增总量**：~275 tokens（WEREWOLF_META_KNOWLEDGE + ANTI_ECHO + NEW_INFO_PRIORITY）
**Optimizer 新增总量**：~175 tokens（PERSONA_DEPTH + 跨轮变化）
**Evaluator 新增总量**：~15 tokens（一条扣分规则）

DeepSeek-Chat 上下文窗口 64K tokens，当前 thinker prompt + 游戏状态约 3000-5000 tokens，新增 275 tokens 完全在预算内。

## 5. Execution Order

1. Part B 先做（prompt 改动独立，无需前端构建验证）
2. Part A 后做（UI 改动需要视觉验证）
3. 两部分可并行，但考虑到验证顺序，建议串行

## Change Log

| Version | Date | Changes | Affected Scope | Reason |
|:---|:---|:---|:---|:---|
| v1 | 2026-03-17 | Initial version | ALL | - |
