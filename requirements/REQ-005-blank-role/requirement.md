# REQ-005 Blank Role Support

> Status: Requirement Finalized
> Created: 2026-03-15
> Updated: 2026-03-15

## 1. Background

当前「谁是卧底」游戏只支持两种角色：平民（civilian）和卧底（spy）。经典桌游中还有一种「白板」角色（blank）——该玩家拿到空白卡，不知道任何词，必须靠听别人的描述来伪装。

本需求新增白板角色支持，包含两种游戏模式：

1. **混合白板模式**（standard + blank）：平民 + 卧底 + 白板共存，白板独立阵营
2. **全员白板模式**（all_blank）：所有玩家都是白板，无词可用，纯社交推理

## 2. Target Users & Scenarios

- **AI 游戏研究者**：观察 LLM agent 在"无信息"条件下的推理和伪装行为
- **娱乐观众**：观看全员白板的混乱喜剧效果
- **场景**：
  - 标准局加入1个白板增加复杂度（6人局：4平民+1卧底+1白板）
  - 全员白板模式：4人都没词，互相猜忌

## 3. Functional Requirements

### F-01: Game Engine — Blank Role Assignment

- **Main flow:**
  - 配置新增 `blank_count` 字段（默认0）
  - 配置新增 `mode` 字段：`"standard"`（默认）或 `"all_blank"`
  - `mode="standard"` 且 `blank_count > 0` 时：在平民/卧底基础上额外分配白板角色
  - `mode="all_blank"` 时：忽略 `spy_count`/`blank_count`，所有玩家设为 `role="blank"`, `word=""`
  - 白板的 `PlayerState`：`role="blank"`, `word=""`
- **Error handling:**
  - `spy_count + blank_count >= len(players)` → 拒绝：非卧底/白板角色至少需要1人
  - `mode="all_blank"` 时玩家数 < 3 → 拒绝
- **Edge cases:**
  - `blank_count=0` 时行为与现有完全一致（向后兼容）
  - `mode="all_blank"` 时 `spy_count` 配置被忽略

### F-02: Game Engine — Win Condition Updates

- **Standard + blank 模式：**
  - 白板与卧底是独立阵营，各自求生
  - 卧底被淘汰 & 白板被淘汰 → 平民胜
  - 卧底或白板任一存活到最后2人 → 对应阵营胜
  - 连续3次平票 → 非平民阵营胜（与现有卧底逻辑一致）
  - `winner` 可能的值：`"civilian"`, `"spy"`, `"blank"`
  - 如果最后2人中同时有卧底和白板 → 两者都算赢，`winner="spy,blank"`（或定义为非平民阵营共赢）
- **All blank 模式：**
  - 最后2名存活者获胜
  - `winner` = 存活者的 player_id 列表，如 `"p1,p3"`
  - 连续3次平票 → 所有存活者获胜
- **Edge cases:**
  - 3人局 + 1白板1卧底1平民：白板或卧底被投出后变成2人，游戏立即结束
  - 全白板4人：淘汰2人后剩2人，游戏结束

### F-03: Game Engine — Private Info for Blank

- **Main flow:**
  - `get_private_info()` 对白板玩家返回 `{"word": "", "is_blank": True}`
  - 白板玩家知道自己没有词（经典玩法）
  - 非白板玩家不知道谁是白板
- **Edge cases:**
  - 全白板模式下每个玩家都收到 `{"word": "", "is_blank": True}`

### F-04: Agent Strategy — Blank Player Prompt

- **Main flow:**
  - 白板玩家的 thinker prompt 需要特殊版本：
    - 不分析"我拿到的词"，而是分析"其他人的描述暗示了什么词"
    - 策略目标：从别人发言中猜词 → 伪装描述 → 避免被识破
  - evaluator/optimizer prompt 增加白板场景的评估标准
  - 全白板模式使用统一的白板 prompt
- **Error handling:**
  - 白板玩家 prompt 中 `{private_info}` 显示"你没有拿到词（白板）"
- **Edge cases:**
  - 全白板模式下所有人用相同 prompt，不需要区分角色策略

### F-05: Game Rules Prompt Update

- **Main flow:**
  - `RULES_PROMPT` 需根据模式动态生成（不再是静态常量）
  - 标准+白板模式：在规则中说明"可能有白板玩家，白板没有词"
  - 全白板模式：规则说明"所有人都没有词，根据对话推理和伪装，最后存活的2人获胜"
  - `get_game_rules_prompt()` 改为根据当前模式返回不同规则文本

### F-06: Configuration

- **Main flow:**
  - `config/games/spy.yaml` 可选新增 `blank_count` 和 `mode` 字段
  - 新增 `config/games/spy_all_blank.yaml` 作为全白板模式预设配置
  - 示例：
    ```yaml
    # spy.yaml (标准+白板)
    spy_count: 1
    blank_count: 1
    players: [...]

    # spy_all_blank.yaml (全白板)
    mode: all_blank
    players: [...]
    ```
- **Edge cases:**
  - `mode` 不写或写 `"standard"` → 走标准流程
  - `blank_count` 不写 → 默认0，向后兼容

### F-07: Script Schema — Role & Winner Extension

- **Main flow:**
  - `PlayerInfo.role` 新增 `"blank"` 值
  - `GameResult.winner` 扩展：除 `"civilian"`, `"spy"` 外，支持 `"blank"` 和复合值如 `"spy,blank"`
  - `GameScript.game.config` 中记录 `mode` 和 `blank_count`
  - TypeScript 类型 `game-script.ts` 同步更新
- **Edge cases:**
  - 全白板模式 `winner` 是存活者 ID 列表（逗号分隔）

### F-08: Frontend — Word Bar Display

- **Main flow:**
  - `Theater.tsx` 顶部词条栏需适配：
    - 标准+白板模式：显示"平民词 | 卧底词 | 白板：无词"
    - 全白板模式：显示"全员白板模式（无词）"
  - 根据 `script.game.config.mode` 或角色分布判断显示方式

### F-09: Frontend — Player Avatar Blank Badge

- **Main flow:**
  - `PlayerAvatar.tsx` 为白板角色显示"白板"徽章（类似卧底的"卧底"徽章）
  - 颜色：用灰色/白色系区分于卧底的红色
  - `word` 为空时显示"无词"标签
- **Edge cases:**
  - 全白板模式下所有人都显示"白板"徽章

### F-10: Frontend — Finale Scene Winner Text

- **Main flow:**
  - `FinaleScene.tsx` 当前只判断 `civilian` / `spy`，需支持：
    - `"blank"` → "白板获胜"
    - `"spy,blank"` → "非平民阵营获胜"
    - 全白板模式 → "存活者获胜：XXX, XXX"
  - winner animation 对白板角色也要有视觉突出（类似 spy 的 pulse 动画）

### F-11: Test — Blank Role Scenarios

- **Main flow:**
  - 在 `test_spy_game.py` 或新建 `test_blank_game.py` 中增加：
    - Scenario: 白板被淘汰（平民胜）
    - Scenario: 白板存活到最后2人（白板胜）
    - Scenario: 全白板模式，正常淘汰至2人
  - 在 `test_script_pipeline.py` 中增加白板场景的结构验证
  - `validate_script()` 需支持 `role="blank"` 和新的 winner 值

## 4. Non-functional Requirements

- 向后兼容：不配置 `blank_count` 和 `mode` 时，行为与现有完全一致
- 现有测试不受影响
- 白板 agent 的 prompt 质量需确保 LLM 能产出合理的"猜词伪装"行为

## 5. Out of Scope

- 白板玩家的"猜词揭示"机制（某些变体中白板被投出后可以猜词，猜对则白板胜）
- 多白板间的团队协作（白板之间不知道彼此身份）
- 前端"白板视角"特殊 UI（如模糊效果）
- 音频/TTS 的角色特殊处理

## 6. Acceptance Criteria

| ID | Feature | Condition | Expected Result |
|:---|:---|:---|:---|
| AC-01 | F-01 | `blank_count=0` 时运行标准局 | 行为与现有完全一致 |
| AC-02 | F-01 | `blank_count=1` 时运行 | 有1个玩家 role=blank, word="" |
| AC-03 | F-01 | `mode=all_blank` 时运行 | 所有玩家 role=blank, word="" |
| AC-04 | F-02 | 标准+白板局，白板被淘汰，卧底也被淘汰 | winner=civilian |
| AC-05 | F-02 | 标准+白板局，白板存活到最后2人 | winner=blank |
| AC-06 | F-02 | 标准+白板局，卧底存活到最后2人 | winner=spy |
| AC-07 | F-02 | 全白板局，淘汰至剩2人 | winner=存活者ID |
| AC-08 | F-03 | 白板玩家查看 private_info | 收到 `is_blank: True` |
| AC-09 | F-04 | 白板 agent 发言 | 不说"我没有词"，而是试图伪装 |
| AC-10 | F-05 | 标准+白板模式规则 | 规则文本提及白板角色 |
| AC-11 | F-05 | 全白板模式规则 | 规则文本说明所有人无词 |
| AC-12 | F-07 | 白板角色的 JSON 输出 | `role="blank"` 且 `word=""` |
| AC-13 | F-08 | 全白板模式前端词条栏 | 显示"全员白板模式" |
| AC-14 | F-09 | 白板角色头像 | 显示"白板"灰色徽章 |
| AC-15 | F-10 | 白板获胜结局 | 显示"白板获胜" |
| AC-16 | F-11 | 所有测试场景 | 全部通过 |

## 7. Change Log

| Version | Date | Changes | Affected Scope | Reason |
|:---|:---|:---|:---|:---|
| v1 | 2026-03-15 | Initial version | ALL | - |
