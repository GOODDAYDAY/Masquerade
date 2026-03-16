# REQ-009 Technical Design

> Status: Completed
> Requirement: requirement.md
> Created: 2026-03-15
> Updated: 2026-03-15

## 1. Technology Stack

无新增技术栈，全部在现有代码上修改。

## 2. Design Principles

- 每个修复点独立，可单独验证
- 保持 agent 层游戏无关性

## 3. Architecture Overview

改动文件清单：

| 文件 | Feature | 改动 |
|:---|:---|:---|
| `backend/engine/spy/game.py` | F-01 | setup() 中 shuffle player_order |
| `backend/engine/werewolf/game.py` | F-01 | setup() 中 shuffle player_order |
| `backend/core/config.py` | F-02 | PlayerConfig 加 voice 字段 |
| `backend/orchestrator/runner.py` | F-02 | 传 voice 映射给 TTS |
| `backend/tts/generate.py` | F-02 | 接受外部 voice_config |
| `backend/engine/spy/strategy.py` | F-03 | thinker prompt 加玩家名单强调 |
| `backend/engine/werewolf/strategy.py` | F-03 | thinker prompt 加玩家名单强调 |
| `backend/agent/nodes/optimizer.py` | F-04 | 优化内容字段识别逻辑 |
| `backend/script/schema.py` | F-05 | PlayerInfo 加 extra 字段 |
| `backend/orchestrator/runner.py` | F-05 | 从 get_role_info 填充 extra |
| `backend/engine/spy/strategy.py` | F-06 | evaluator prompt 加 private_info |
| `backend/engine/werewolf/strategy.py` | F-06 | evaluator prompt 加 private_info |
| `backend/agent/nodes/evaluator.py` | F-06 | 传 private_info 到 prompt format |

## 4. Module Design

### 4.1 F-01: 玩家顺序随机化

**SpyGame.setup()：**
```python
self.player_order = list(players)
random.shuffle(self.player_order)  # NEW
```

**WerewolfGame.setup()：**
```python
self.player_order = list(players)
random.shuffle(self.player_order)  # NEW
```

角色分配在 shuffle 之后，用 index 对 `players`（原始列表）分配角色，不受 shuffle 影响。

### 4.2 F-02: TTS 音色配置

**PlayerConfig（config.py）：**
```python
class PlayerConfig(BaseModel):
    name: str
    model: str = ""
    api_base: str = ""
    api_key: str = ""
    persona: str = ""
    appearance: str = ""
    voice: str = ""  # NEW: edge-tts voice name, empty = auto-assign
```

**Runner._generate_tts()：** 传入 voice 映射
```python
async def _generate_tts(self, script_path: str) -> None:
    # Build voice_config from player configs
    voice_config = {}
    for pc in self._player_configs:
        if pc.voice:
            voice_config[pc.name] = pc.voice
    # Pass to generate_audio
    await generate_audio(script_path, voice_config=voice_config or None)
```

**generate.py：** `generate_audio` 已接受 `voice_config` 参数，需确认接口一致。如果当前不接受，加上参数透传到 `assign_voices()`。

**YAML 配置示例：**
```yaml
players:
  - name: "甄暴躁"
    persona: "..."
    voice: "zh-CN-YunjianNeural"  # 可选
```

### 4.3 F-03: Prompt 强调玩家名称

**核心改动：** 在所有 thinker prompt 的末尾追加一段强制指令：

```
**【重要】你必须使用玩家的真实名字（如"甄暴躁"、"甄冷静"），绝对不能使用编号（如"1号"、"3号"、"玩家B"等）。**
当前存活玩家名字列表：{alive_players}
```

`{alive_players}` 已经在 `{public_state}` 中包含，但不够醒目。改为在 prompt 模板中**单独列出**。

**实现方式：** thinker_node 在格式化 prompt 时，从 public_state 中提取 alive_players 并注入。需要在 prompt 模板中添加 `{alive_players}` 占位符，或在 thinker_node 中追加。

**选择后者更通用：** thinker_node.py 在 user_prompt 末尾追加玩家名单提醒，不修改具体游戏的 prompt 模板。这样所有游戏自动受益。

```python
# thinker_node.py — append player name reminder
alive_players = state.get("public_state", {}).get("alive_players", [])
if alive_players:
    user_prompt += "\n\n【重要提醒】当前存活玩家名字：%s。你必须使用这些真实名字，绝对不能用编号或代号。" % "、".join(alive_players)
```

### 4.4 F-04: Optimizer 内容字段识别

**当前问题：** `_get_content_field()` 把 `gesture`（"你的动作描述"）识别为文本字段，触发 LLM 润色，结果把动作描述搞成了 "玩家B"。

**修复方案：** 增加"需要润色"的正向关键词判断，而非仅排除 target 字段。只有 description 中包含"发言""内容""说""遗言"等明确表示自然语言输出的字段才做润色。

```python
_OPTIMIZE_DESC_HINTS = ("发言", "内容", "说", "看法", "推理", "遗言")

def _get_content_field(action_type, tools_schema):
    # Find the first required field whose description suggests
    # natural language content that benefits from polishing
    for tool in tools_schema:
        if tool.get("function", {}).get("name") == action_type:
            params = tool["function"].get("parameters", {})
            for field_name in params.get("required", []):
                prop = params.get("properties", {}).get(field_name, {})
                desc = prop.get("description", "")
                if any(hint in desc for hint in _OPTIMIZE_DESC_HINTS):
                    return field_name
            return None  # No optimizable field found
    return None
```

这样 `gesture`（"你的动作描述"）不包含"发言/内容/说"等关键词 → 不会被润色。`content`（"你的发言内容"）包含"发言""内容" → 会被润色。

### 4.5 F-05: PlayerInfo 通用化

**schema.py：**
```python
class PlayerInfo(BaseModel):
    id: str
    name: str
    model: str = ""
    persona: str = ""
    appearance: str = ""
    role: str = ""
    word: str = ""  # Spy-specific, kept for backward compat
    extra: dict = Field(default_factory=dict)  # NEW: game-specific data
```

**Runner 填充：**
```python
role_info = engine.get_role_info(pc.name)
player_infos.append(PlayerInfo(
    id=pc.name,
    name=pc.name,
    model=pc.model,
    persona=pc.persona,
    appearance=pc.appearance,
    role=role_info.pop("role", ""),
    word=role_info.pop("word", ""),
    extra=role_info,  # Remaining fields go to extra
))
```

这样 WerewolfGame 的 `get_role_info()` 返回 `{"role": "werewolf", "faction": "wolf"}` 时，`faction` 自动进入 `extra`。

**Frontend TypeScript：**
```typescript
export interface PlayerInfo {
    // ... existing ...
    extra?: Record<string, unknown>;
}
```

### 4.6 F-06: Evaluator 改善规则理解

**问题：** evaluator LLM 看到 "不能连续保护同一人" 就判违规，但不知道这是第一晚、上次没保护过任何人。

**修复：** 在 evaluator prompt 调用时加入 private_info 上下文。

**evaluator_node.py 修改：**
```python
prompt = prompt_template.format(
    situation_analysis=...,
    strategy=...,
    action_type=...,
    action_payload=...,
    private_info=json.dumps(state.get("private_info", {}), ensure_ascii=False),  # NEW
)
```

**所有 evaluator prompt 模板修改：** 添加 `{private_info}` 占位符和提示：

```
玩家的私有信息（用于判断规则合法性）：
{private_info}
```

这样 evaluator LLM 能看到 `last_protected: null`（第一晚），就不会误判"连续保护"。

## 5. Data Model

PlayerInfo 新增 `extra: dict`，其余无新增。

## 6. API Design

无新增。

## 7. Key Flows

无新增流程，均为现有流程的修正。

## 8. Shared Modules & Reuse Strategy

| 改动 | 共享性 |
|:---|:---|
| thinker_node 追加玩家名单 | 所有游戏自动受益 |
| optimizer 内容字段识别 | 所有游戏自动受益 |
| evaluator 加 private_info | 所有游戏自动受益 |
| PlayerInfo.extra | 所有游戏通用 |

## 9. Risks & Notes

| 风险 | 缓解 |
|:---|:---|
| shuffle 影响现有测试（固定 seed 结果变化） | 测试中使用 random.seed 固定 |
| 旧 evaluator prompt 无 {private_info} 占位符 | 所有 evaluator prompt 模板需同步添加 |
| PlayerInfo.extra 影响前端 | 前端 TypeScript 加 optional 字段，旧 JSON 兼容 |

## 10. Change Log

| Version | Date | Changes | Affected Scope | Reason |
|:---|:---|:---|:---|:---|
| v1 | 2026-03-15 | Initial version | ALL | - |
