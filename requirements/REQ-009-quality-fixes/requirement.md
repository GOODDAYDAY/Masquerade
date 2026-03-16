# REQ-009 Game Quality Fixes & Generalization

> Status: Completed
> Created: 2026-03-15
> Updated: 2026-03-15

## 1. Background

首次实际运行狼人杀游戏暴露了多个问题：LLM 用编号而非玩家名字、Optimizer 破坏动作描述、evaluator LLM 误判规则、白板可能第一个发言、PlayerInfo 不通用、TTS 无法配置音色。这些问题涉及多个模块，需要综合修复。

## 2. Target Users & Scenarios

- **开发者/用户：** 运行狼人杀或谁是卧底游戏时，AI 能正确使用玩家名字、游戏流程顺畅、TTS 音色可配置

## 3. Functional Requirements

### F-01 玩家发言顺序随机化

- **SpyGame：** `setup()` 中对 `player_order` 进行 `random.shuffle()`，确保白板不总是第一个发言
- **WerewolfGame：** 同理，`player_order` 随机打乱
- **边界：** 角色分配在 shuffle 之后进行，不影响角色随机性

### F-02 TTS 音色配置

- **PlayerConfig 新增 `voice: str = ""` 字段**
- **werewolf.yaml / spy.yaml 可选配置 voice**
- **Runner 在生成 TTS 时传入 voice 映射**
- **TTS 模块已支持 voice_config 参数，仅需 Runner 接入**
- **无配置时使用现有轮询逻辑，有配置的玩家使用指定音色**

### F-03 Prompt 强调使用玩家名称

- **所有游戏的 thinker prompt 中，明确列出所有存活玩家名字**
- **强调"必须使用玩家的真实名字，不能用编号、代号、字母"**
- **投票/目标选择时提示"从以下名字中选择：xxx, yyy, zzz"**
- **涉及文件：** spy/strategy.py, werewolf/strategy.py 中的 thinker prompt

### F-04 Optimizer 不破坏非文本内容

- **问题：** wolf_discuss 的 gesture 字段被 optimizer "润色"后变成 "玩家B"、"3" 等无意义内容
- **根因：** `_get_content_field()` 把 gesture 识别为"文本字段"，走了 LLM 润色
- **修复：** 只对 description 中包含"发言""说""内容"等关键词的字段做润色，gesture 类字段跳过或保持原样
- **更好的方案：** engine 在 tools_schema 中标记哪些字段需要润色（通过 description 关键词区分即可）

### F-05 PlayerInfo 通用化

- **问题：** `word` 字段是 Spy 游戏特有概念，狼人杀被迫填空
- **方案：** PlayerInfo 新增 `extra: dict = {}` 通用字段，engine 的 `get_role_info()` 返回的所有信息都放入 extra
- **保留 role 字段（通用）**，`word` 字段保留向后兼容但标记为 Spy 专用
- **前端按需从 extra 中读取游戏特有信息**

### F-06 Evaluator LLM 改善规则理解

- **问题：** LLM evaluator 误判"连续保护同一人"——第一晚 guard 从未保护过任何人，LLM 却判违规
- **根因：** evaluator prompt 没有足够的上下文（不知道这是第一晚、不知道上次保护了谁）
- **修复：** 在 evaluator 调用时，将 private_info（含 last_protected 等状态）传入 evaluator prompt，让 LLM 有足够信息做判断
- **具体：** evaluator prompt 模板增加 `{private_info}` 占位符，调用时填入

## 4. Non-functional Requirements

- **NF-01：** 现有测试在修改后全部通过
- **NF-02：** 不新增 LLM 调用次数

## 5. Out of Scope

- 日志初始化冗余优化（保持现状）
- 前端对 PlayerInfo.extra 的展示适配（后续需求）
- player_id 和 name 的分离（当前统一即可）

## 6. Acceptance Criteria

| ID | Feature | Condition | Expected Result |
|:---|:---|:---|:---|
| AC-01 | F-01 | SpyGame setup 后 player_order | 与输入顺序不同（随机打乱） |
| AC-02 | F-01 | WerewolfGame setup 后 player_order | 与输入顺序不同（随机打乱） |
| AC-03 | F-02 | PlayerConfig 有 voice 字段 | 可选，默认空 |
| AC-04 | F-02 | werewolf.yaml 配置 voice 后 | TTS 使用指定音色 |
| AC-05 | F-03 | thinker prompt 中 | 包含存活玩家名字列表 |
| AC-06 | F-03 | LLM 投票/选择目标时 | 使用玩家真实名字而非编号 |
| AC-07 | F-04 | wolf_discuss gesture 经过 optimizer | 内容不被破坏 |
| AC-08 | F-05 | PlayerInfo 包含 extra 字段 | 默认空 dict |
| AC-09 | F-05 | 狼人杀 get_role_info 返回 faction | 记录在 PlayerInfo.extra 中 |
| AC-10 | F-06 | 第一晚守卫保护合法目标 | evaluator LLM 不误判违规 |
| AC-11 | NF-01 | 运行所有现有测试 | 全部通过 |

## 7. Change Log

| Version | Date | Changes | Affected Scope | Reason |
|:---|:---|:---|:---|:---|
| v1 | 2026-03-15 | Initial version | ALL | - |
