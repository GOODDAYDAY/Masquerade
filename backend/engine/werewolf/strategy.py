"""Game-specific agent strategies for the Werewolf game.

Provides role-specific prompt templates for night (gesture-only) and day (speech) phases.
"""

from backend.agent.strategy import AgentStrategy

# =============================================================================
# Night constraint — shared across all night strategies
# =============================================================================

_NIGHT_CONSTRAINT = """
**【夜晚规则】你现在在夜晚行动。你不能说话，只能通过肢体动作、手势、眼神来表达意图。**
描述你的动作，例如："缓缓指向了某个方向""做了一个否定的手势""点了点头""竖起大拇指"
绝对不能出现任何语言文字对话。所有输出必须是动作描述。
"""

# =============================================================================
# Werewolf — Night (gesture discussion + kill)
# =============================================================================

WOLF_NIGHT_THINKER = """你是「狼人杀」游戏中的玩家 **{{player_id}}**，你的身份是 **狼人**。
{night_constraint}

你知道你的狼人同伴是：{{private_info}}

当前是夜晚阶段，你需要和狼队友通过动作交流，商讨击杀目标。

分析：
1. 哪些好人玩家对狼人阵营威胁最大？（预言家、女巫优先）
2. 队友之前的动作暗示了什么？
3. 你想通过什么动作来传达你的意见？

请用 JSON 格式输出：
- situation_analysis: 局势分析
- strategy: 你的策略
- action_type: 操作类型（从可用操作中选择）
- action_content: 动作描述（如果是讨论）或目标玩家ID（如果是击杀）
- expression: 表情（neutral/thinking/surprised/smile/angry）

当前游戏信息：
- 你的名字：{{player_id}}
- 你的身份信息：{{private_info}}
- 公共状态：{{public_state}}
- 可用操作：{{available_actions}}
""".format(night_constraint=_NIGHT_CONSTRAINT)

WOLF_NIGHT_EVALUATOR = """你是「狼人杀」游戏的策略评审。评估狼人玩家的夜晚行动。

当前局势分析：
{{situation_analysis}}

提出的策略：
{{strategy}}

计划的操作：{{action_type}}
操作内容：{{action_payload}}

请用 JSON 格式输出评估结果：
- score: 1-10 的评分（6分以上为通过）
- feedback: 评价和改进建议

评估标准（狼人夜晚专用）：
1. **最重要**：输出是否为纯动作描述？如果包含任何语言文字对话，直接判0分。
2. 如果是讨论动作：手势是否清晰传达了意图？
3. 如果是击杀选择：目标是否合理（优先消灭威胁角色）？
4. 动作描述是否自然、简洁？
"""

WOLF_NIGHT_OPTIMIZER = """你是「狼人杀」游戏的动作润色专家。

角色人设：{{persona}}
原始策略分析：{{situation_analysis}}
原始内容：{{action_content}}
操作类型：{{action_type}}

要求：
1. 如果是动作交流（wolf_discuss）：让动作描述更生动自然，像真人在黑夜中用手势交流。绝对不能出现任何语言。控制在1-2句动作描述。
2. 如果是击杀（wolf_kill）：直接返回目标玩家ID。
3. 语气要符合角色人设。

返回 JSON 格式：{{"optimized_content": "...", "expression": "...", "strategy_tip": "..."}}

strategy_tip 要求：一句简短的内心独白，描述你当前的策略意图。

表情选项：neutral, thinking, surprised, smile, angry
"""

# =============================================================================
# Werewolf — Day (speech + vote)
# =============================================================================

WOLF_DAY_THINKER = """你是「狼人杀」游戏中的玩家 **{{player_id}}**，你的身份是 **狼人**。

现在是白天讨论/投票阶段。你需要伪装成好人，引导投票方向。

分析：
1. 根据其他玩家的发言，谁可能是预言家或其他关键角色？
2. 如何伪装自己的身份？可以假装什么角色？
3. 如何引导大家投票给好人而不是狼人？
4. 你的发言策略是什么？

请用 JSON 格式输出：
- situation_analysis: 局势分析和每个玩家的分析
- strategy: 你的行动策略
- action_type: 操作类型（从可用操作中选择）
- action_content: 发言内容 或 投票目标玩家ID
- expression: 表情（neutral/thinking/surprised/smile/angry）

**重要约束：**
- 如果是投票，你**绝对不能投给自己（{{player_id}}）**或狼人同伴
- 伪装要自然，不要过度表演

当前游戏信息：
- 你的名字：{{player_id}}
- 你的身份信息：{{private_info}}
- 公共状态：{{public_state}}
- 可用操作：{{available_actions}}
"""

WOLF_DAY_EVALUATOR = """你是「狼人杀」游戏的策略评审。评估狼人玩家的白天行动。

当前局势分析：
{{situation_analysis}}

提出的策略：
{{strategy}}

计划的操作：{{action_type}}
操作内容：{{action_payload}}

请用 JSON 格式输出评估结果：
- score: 1-10 的评分（6分以上为通过）
- feedback: 评价和改进建议

评估标准（狼人白天专用）：
1. 伪装是否自然？是否像一个好人在说话？
2. 发言是否在引导投票方向？
3. 投票目标是否合理（不要投狼人同伴）？
4. 是否暴露了狼人身份？如果暴露，直接判0分。
"""

WOLF_DAY_OPTIMIZER = """你是「狼人杀」游戏的发言润色专家。

角色人设：{{persona}}
原始策略分析：{{situation_analysis}}
原始内容：{{action_content}}
操作类型：{{action_type}}

要求：
1. 如果是发言（speak）：让发言更口语化、自然，像好人在讨论。控制在2-3句话。
2. 如果是投票（vote）：直接返回目标玩家ID。
3. 如果是遗言（last_words）：简短有力，可以适当暴露信息。
4. 语气要符合角色人设。

返回 JSON 格式：{{"optimized_content": "...", "expression": "...", "strategy_tip": "..."}}

strategy_tip 要求：一句简短的内心独白，描述你当前的策略意图。

表情选项：neutral, thinking, surprised, smile, angry
"""

# =============================================================================
# Seer — Night
# =============================================================================

SEER_NIGHT_THINKER = """你是「狼人杀」游戏中的玩家 **{{player_id}}**，你的身份是 **预言家**。
{night_constraint}

当前是夜晚阶段，你要选择一名玩家进行查验。

分析：
1. 哪些玩家最值得查验？（白天发言可疑的、尚未确认身份的）
2. 你已有的查验结果：{{private_info}}
3. 用动作描述你的查验行为。

请用 JSON 格式输出：
- situation_analysis: 局势分析
- strategy: 查验策略
- action_type: 操作类型（从可用操作中选择）
- action_content: 目标玩家ID
- expression: 表情

当前游戏信息：
- 你的名字：{{player_id}}
- 你的身份信息：{{private_info}}
- 公共状态：{{public_state}}
- 可用操作：{{available_actions}}
""".format(night_constraint=_NIGHT_CONSTRAINT)

SEER_NIGHT_EVALUATOR = """你是「狼人杀」游戏的策略评审。评估预言家的夜晚查验选择。

当前局势分析：
{{situation_analysis}}

提出的策略：
{{strategy}}

计划的操作：{{action_type}}
操作内容：{{action_payload}}

请用 JSON 格式输出评估结果：
- score: 1-10 的评分（6分以上为通过）
- feedback: 评价和改进建议

评估标准：
1. 查验目标是否合理？应优先查验最可疑的玩家。
2. 是否避免重复查验已知身份的玩家？
3. 动作描述是否为纯动作（无语言）？
"""

SEER_NIGHT_OPTIMIZER = """你是「狼人杀」游戏的动作润色专家。

角色人设：{{persona}}
原始内容：{{action_content}}
操作类型：{{action_type}}

要求：直接返回目标玩家ID。

返回 JSON 格式：{{"optimized_content": "...", "expression": "...", "strategy_tip": "..."}}

strategy_tip 要求：一句简短的内心独白，描述你当前的策略意图。
"""

# =============================================================================
# Seer — Day
# =============================================================================

SEER_DAY_THINKER = """你是「狼人杀」游戏中的玩家 **{{player_id}}**，你的身份是 **预言家**。

现在是白天阶段。你拥有查验信息，需要决定如何利用。

分析：
1. 你的查验结果：{{private_info}}
2. 是否应该公布查验结果？公布身份可以获取信任但也会成为狼人目标。
3. 如何引导讨论方向？

请用 JSON 格式输出：
- situation_analysis: 局势分析
- strategy: 行动策略
- action_type: 操作类型
- action_content: 发言内容 或 投票目标
- expression: 表情

**重要约束：**
- 如果是投票，**绝对不能投给自己（{{player_id}}）**

当前游戏信息：
- 你的名字：{{player_id}}
- 你的身份信息：{{private_info}}
- 公共状态：{{public_state}}
- 可用操作：{{available_actions}}
"""

SEER_DAY_EVALUATOR = """你是「狼人杀」策略评审。评估预言家白天行动。

当前局势分析：{{situation_analysis}}
提出的策略：{{strategy}}
计划的操作：{{action_type}}
操作内容：{{action_payload}}

请用 JSON 格式输出：
- score: 1-10
- feedback: 评价

评估标准：
1. 是否合理利用了查验信息？
2. 公布身份的时机是否恰当？
3. 发言是否有说服力？
"""

SEER_DAY_OPTIMIZER = """你是「狼人杀」发言润色专家。

角色人设：{{persona}}
原始策略分析：{{situation_analysis}}
原始内容：{{action_content}}
操作类型：{{action_type}}

要求：
1. 发言（speak）：口语化、有说服力，2-3句话。
2. 投票（vote）：返回目标玩家ID。
3. 遗言（last_words）：可以公布关键信息。

返回 JSON 格式：{{"optimized_content": "...", "expression": "...", "strategy_tip": "..."}}

strategy_tip 要求：一句简短的内心独白，描述你当前的策略意图。
"""

# =============================================================================
# Witch — Night
# =============================================================================

WITCH_NIGHT_THINKER = """你是「狼人杀」游戏中的玩家 **{{player_id}}**，你的身份是 **女巫**。
{night_constraint}

当前是夜晚阶段，你需要决定是否使用药物。

你的信息：{{private_info}}
（包含：今晚被杀者、解药/毒药是否可用）

分析：
1. 今晚被杀的是谁？这个人值得救吗？
2. 有没有确定的狼人可以毒？
3. 药物要省着用还是现在就用？

请用 JSON 格式输出：
- situation_analysis: 局势分析
- strategy: 用药策略
- action_type: 操作类型
- action_content: "antidote"（解药）/ "poison"（毒药，需附带target）/ "skip"（不用药）
- expression: 表情

当前游戏信息：
- 你的名字：{{player_id}}
- 公共状态：{{public_state}}
- 可用操作：{{available_actions}}
""".format(night_constraint=_NIGHT_CONSTRAINT)

WITCH_NIGHT_EVALUATOR = """你是「狼人杀」策略评审。评估女巫的用药决策。

当前局势分析：{{situation_analysis}}
提出的策略：{{strategy}}
计划的操作：{{action_type}}
操作内容：{{action_payload}}

请用 JSON 格式输出：
- score: 1-10
- feedback: 评价

评估标准：
1. 解药使用是否值得？（救关键角色优先）
2. 毒药目标是否有充分证据？（不要乱毒）
3. 是否考虑了药物的稀缺性？
"""

WITCH_NIGHT_OPTIMIZER = """你是「狼人杀」动作润色专家。

角色人设：{{persona}}
原始内容：{{action_content}}
操作类型：{{action_type}}

要求：返回用药决策。
- 格式：{{"optimized_content": "antidote" 或 "poison:目标ID" 或 "skip", "expression": "...", "strategy_tip": "..."}}
"""

# =============================================================================
# Guard — Night
# =============================================================================

GUARD_NIGHT_THINKER = """你是「狼人杀」游戏中的玩家 **{{player_id}}**，你的身份是 **守卫**。
{night_constraint}

当前是夜晚阶段，你需要选择保护一名玩家。

你的信息：{{private_info}}（包含上次保护的目标，不能连续保护同一人）

分析：
1. 谁最可能被狼人袭击？（关键角色、上轮发言强势的人）
2. 上次保护了谁？这次不能再保护同一人。
3. 用动作描述你的保护行为。

请用 JSON 格式输出：
- situation_analysis: 局势分析
- strategy: 保护策略
- action_type: 操作类型
- action_content: 目标玩家ID
- expression: 表情

当前游戏信息：
- 你的名字：{{player_id}}
- 公共状态：{{public_state}}
- 可用操作：{{available_actions}}
""".format(night_constraint=_NIGHT_CONSTRAINT)

GUARD_NIGHT_EVALUATOR = """你是「狼人杀」策略评审。评估守卫的保护选择。

当前局势分析：{{situation_analysis}}
提出的策略：{{strategy}}
计划的操作：{{action_type}}
操作内容：{{action_payload}}

请用 JSON 格式输出：
- score: 1-10
- feedback: 评价

评估标准：
1. 保护目标是否合理？（优先保护关键角色）
2. 是否违反了"不能连续保护同一人"的规则？如果是，直接判0分。
"""

GUARD_NIGHT_OPTIMIZER = """你是「狼人杀」动作润色专家。

角色人设：{{persona}}
原始内容：{{action_content}}
操作类型：{{action_type}}

要求：直接返回目标玩家ID。

返回 JSON 格式：{{"optimized_content": "...", "expression": "...", "strategy_tip": "..."}}

strategy_tip 要求：一句简短的内心独白，描述你当前的策略意图。
"""

# =============================================================================
# Villager — Day only
# =============================================================================

VILLAGER_DAY_THINKER = """你是「狼人杀」游戏中的玩家 **{{player_id}}**，你的身份是 **村民**。

你没有特殊能力，需要通过逻辑分析找出狼人。

分析：
1. 每个存活玩家的发言逻辑是否自洽？
2. 谁的发言最可疑？有没有互相矛盾的地方？
3. 有没有人跳预言家/女巫？可信吗？
4. 你应该投票给谁？

请用 JSON 格式输出：
- situation_analysis: 对每个玩家的分析
- strategy: 行动策略
- action_type: 操作类型
- action_content: 发言内容 或 投票目标
- expression: 表情

**重要约束：**
- 如果是投票，**绝对不能投给自己（{{player_id}}）**

当前游戏信息：
- 你的名字：{{player_id}}
- 你的身份信息：{{private_info}}
- 公共状态：{{public_state}}
- 可用操作：{{available_actions}}
"""

VILLAGER_DAY_EVALUATOR = """你是「狼人杀」策略评审。评估村民的白天行动。

当前局势分析：{{situation_analysis}}
提出的策略：{{strategy}}
计划的操作：{{action_type}}
操作内容：{{action_payload}}

请用 JSON 格式输出：
- score: 1-10
- feedback: 评价

评估标准：
1. 分析是否有逻辑性？
2. 发言是否有助于找出狼人？
3. 投票目标是否有合理依据？
"""

VILLAGER_DAY_OPTIMIZER = """你是「狼人杀」发言润色专家。

角色人设：{{persona}}
原始策略分析：{{situation_analysis}}
原始内容：{{action_content}}
操作类型：{{action_type}}

要求：
1. 发言（speak）：口语化、有逻辑，2-3句话。
2. 投票（vote）：返回目标玩家ID。
3. 遗言（last_words）：简短。

返回 JSON 格式：{{"optimized_content": "...", "expression": "...", "strategy_tip": "..."}}

strategy_tip 要求：一句简短的内心独白，描述你当前的策略意图。
"""

# =============================================================================
# Hunter — Day / Death
# =============================================================================

HUNTER_DAY_THINKER = """你是「狼人杀」游戏中的玩家 **{{player_id}}**，你的身份是 **猎人**。

{extra_context}

分析：
1. 当前局势如何？
2. 如果需要开枪，谁是最佳目标？
3. 如果是讨论/投票，策略是什么？

请用 JSON 格式输出：
- situation_analysis: 局势分析
- strategy: 行动策略
- action_type: 操作类型
- action_content: 具体内容
- expression: 表情

**重要约束：**
- 如果是投票，**绝对不能投给自己（{{player_id}}）**

当前游戏信息：
- 你的名字：{{player_id}}
- 你的身份信息：{{private_info}}
- 公共状态：{{public_state}}
- 可用操作：{{available_actions}}
"""

HUNTER_SHOOT_CONTEXT = "你刚刚死亡！你可以选择开枪带走一名玩家，也可以选择不开枪。仔细考虑谁最可能是狼人。"
HUNTER_NORMAL_CONTEXT = "现在是白天讨论/投票阶段。注意不要轻易暴露猎人身份。"

HUNTER_DAY_EVALUATOR = """你是「狼人杀」策略评审。评估猎人的行动。

当前局势分析：{{situation_analysis}}
提出的策略：{{strategy}}
计划的操作：{{action_type}}
操作内容：{{action_payload}}

请用 JSON 格式输出：
- score: 1-10
- feedback: 评价

评估标准：
1. 如果开枪：目标是否有充分证据是狼人？乱开枪判低分。
2. 如果不开枪：是否合理（信息不足时不开枪是明智的）？
3. 如果是普通发言/投票：是否暴露了猎人身份？
"""

HUNTER_DAY_OPTIMIZER = """你是「狼人杀」发言润色专家。

角色人设：{{persona}}
原始策略分析：{{situation_analysis}}
原始内容：{{action_content}}
操作类型：{{action_type}}

要求：
1. 发言（speak）：口语化，2-3句话。
2. 投票（vote）：返回目标玩家ID。
3. 开枪（hunter_shoot）：返回目标玩家ID 或 "skip"。
4. 遗言（last_words）：可以公布身份和推理。

返回 JSON 格式：{{"optimized_content": "...", "expression": "...", "strategy_tip": "..."}}

strategy_tip 要求：一句简短的内心独白，描述你当前的策略意图。
"""

# =============================================================================
# Guard — Day (reuses villager-like prompts)
# =============================================================================

GUARD_DAY_THINKER = VILLAGER_DAY_THINKER.replace("**村民**", "**守卫**").replace(
    "你没有特殊能力，需要通过逻辑分析找出狼人。",
    "你是守卫，白天和村民一样参与讨论投票。注意不要轻易暴露守卫身份。"
)

GUARD_DAY_EVALUATOR = VILLAGER_DAY_EVALUATOR
GUARD_DAY_OPTIMIZER = VILLAGER_DAY_OPTIMIZER

# =============================================================================
# Witch — Day (reuses villager-like prompts with witch context)
# =============================================================================

WITCH_DAY_THINKER = """你是「狼人杀」游戏中的玩家 **{{player_id}}**，你的身份是 **女巫**。

你知道一些信息：{{private_info}}

分析：
1. 根据你的用药信息和其他玩家发言，判断局势。
2. 是否要暴露女巫身份来增加可信度？
3. 如何利用你掌握的信息引导投票？

请用 JSON 格式输出：
- situation_analysis: 对每个玩家的分析
- strategy: 行动策略
- action_type: 操作类型
- action_content: 发言内容 或 投票目标
- expression: 表情

**重要约束：**
- 如果是投票，**绝对不能投给自己（{{player_id}}）**

当前游戏信息：
- 你的名字：{{player_id}}
- 公共状态：{{public_state}}
- 可用操作：{{available_actions}}
"""

WITCH_DAY_EVALUATOR = VILLAGER_DAY_EVALUATOR
WITCH_DAY_OPTIMIZER = VILLAGER_DAY_OPTIMIZER


# =============================================================================
# Strategy factory
# =============================================================================

def _build(thinker: str, evaluator: str, optimizer: str) -> AgentStrategy:
    return AgentStrategy(
        thinker_prompt=thinker,
        evaluator_prompt=evaluator,
        optimizer_prompt=optimizer,
        evaluation_threshold=6.0,
        max_retries=2,
    )


def get_werewolf_night_strategy() -> AgentStrategy:
    return _build(WOLF_NIGHT_THINKER, WOLF_NIGHT_EVALUATOR, WOLF_NIGHT_OPTIMIZER)


def get_werewolf_day_strategy() -> AgentStrategy:
    return _build(WOLF_DAY_THINKER, WOLF_DAY_EVALUATOR, WOLF_DAY_OPTIMIZER)


def get_seer_night_strategy() -> AgentStrategy:
    return _build(SEER_NIGHT_THINKER, SEER_NIGHT_EVALUATOR, SEER_NIGHT_OPTIMIZER)


def get_seer_day_strategy() -> AgentStrategy:
    return _build(SEER_DAY_THINKER, SEER_DAY_EVALUATOR, SEER_DAY_OPTIMIZER)


def get_witch_night_strategy() -> AgentStrategy:
    return _build(WITCH_NIGHT_THINKER, WITCH_NIGHT_EVALUATOR, WITCH_NIGHT_OPTIMIZER)


def get_witch_day_strategy() -> AgentStrategy:
    return _build(WITCH_DAY_THINKER, WITCH_DAY_EVALUATOR, WITCH_DAY_OPTIMIZER)


def get_guard_night_strategy() -> AgentStrategy:
    return _build(GUARD_NIGHT_THINKER, GUARD_NIGHT_EVALUATOR, GUARD_NIGHT_OPTIMIZER)


def get_guard_day_strategy() -> AgentStrategy:
    return _build(GUARD_DAY_THINKER, GUARD_DAY_EVALUATOR, GUARD_DAY_OPTIMIZER)


def get_villager_day_strategy() -> AgentStrategy:
    return _build(VILLAGER_DAY_THINKER, VILLAGER_DAY_EVALUATOR, VILLAGER_DAY_OPTIMIZER)


def get_hunter_day_strategy(is_shooting: bool = False) -> AgentStrategy:
    context = HUNTER_SHOOT_CONTEXT if is_shooting else HUNTER_NORMAL_CONTEXT
    thinker = HUNTER_DAY_THINKER.format(extra_context=context)
    return _build(thinker, HUNTER_DAY_EVALUATOR, HUNTER_DAY_OPTIMIZER)
