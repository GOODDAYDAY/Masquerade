"""Game-specific agent strategy for the Spy game.

Defines prompt templates that tell the agent nodes HOW to think,
evaluate, and optimize specifically for Who Is The Spy.
"""

from backend.agent.strategy import AgentStrategy
from backend.engine.shared_prompts import ANTI_NAME_BIAS, VOTING_EVIDENCE_RULES

SPY_THINKER_PROMPT = """你是「谁是卧底」游戏中的玩家 **{{player_id}}**，正在进行策略分析。

注意：你就是 {{player_id}}，分析其他玩家时不要把自己当成别人。
{anti_name_bias}

根据当前局势，完成以下**深度分析**：

**1. 多假设词语推理（必须完成）：**
- 你拿到的词是什么？
- 列出2-3组可能的词语对（平民词 vs 卧底词），并为每组给出置信度（百分比）
- 根据每个人的描述，哪组词语对最合理？为什么？
- 你认为自己是平民还是卧底？给出概率判断

**2. 证据链分析（逐人分析）：**
- 每个**其他**存活玩家的可疑程度分析
- 必须引用其具体描述内容，指出与多数人描述的异同
- 对比候选人之间的可疑程度差异

**3. 轮次递进分析：**
- 第1轮：信息有限，以收集信息为主，描述要安全但不能太泛
- 第2轮及以后：交叉验证前几轮的描述，找出矛盾点
- 最终轮：高置信度判断，果断行动

**4. 行动策略：**
- 如果是发言：制定自适应描述策略——不能与之前任何人的描述重叠，从新角度切入
- 如果你可能是卧底：描述要向平民词方向靠拢，但不能太明显
- 如果是投票：基于证据链选择目标

{voting_evidence_rules}

请用 JSON 格式输出：
- situation_analysis: 对局势和每个玩家的分析（包含多假设推理）
- strategy: 你的行动策略
- action_type: 操作类型（从可用操作中选择）
- action_content: 具体内容（发言内容 或 投票目标玩家ID）
- expression: 表情（neutral/thinking/surprised/smile/angry）

**重要约束：**
- 如果是投票，你**绝对不能投给自己（{{player_id}}）**，必须投给其他存活玩家
- 如果是发言，不能直接说出词语本身，也不能重复之前任何人说过的描述

当前游戏信息：
- 你的名字：{{player_id}}
- 你的词语：{{private_info}}
- 公共状态：{{public_state}}
- 可用操作：{{available_actions}}
""".format(anti_name_bias=ANTI_NAME_BIAS, voting_evidence_rules=VOTING_EVIDENCE_RULES)

SPY_EVALUATOR_PROMPT = """你是「谁是卧底」游戏的策略评审。评估以下玩家策略是否合理。
{anti_name_bias}

当前局势分析：
{{situation_analysis}}

提出的策略：
{{strategy}}

计划的操作：{{action_type}}
操作内容：{{action_payload}}

玩家私有信息（用于判断规则合法性）：
{{private_info}}

请用 JSON 格式输出评估结果：
- score: 1-10 的评分（6分以上为通过）
- feedback: 评价和改进建议

评估标准（谁是卧底专用）：
1. 如果是发言：是否太直接暴露了词语？好的描述应该含糊但有关联性。
2. 如果是发言：是否重复了之前任何人说过的描述？重复描述直接判0分。每次必须从新角度描述。
3. 如果是投票：投票目标是否有充分的可疑理由？不能乱投。
4. 如果玩家可能是卧底：策略是否在伪装？还是在暴露自己？
5. 表达是否自然、像真人在玩游戏？
6. 是否有考虑到之前轮次的信息？
7. **名字偏见检查（-3分）：** 如果推理中将玩家名字作为判断依据（如"他叫甄大胆所以他肯定会..."），直接扣3分。
8. **投票证据检查（-3分）：** 如果投票时没有引用任何具体发言或行为作为证据，扣3分。
9. **多轮意识检查（-2分）：** 如果在第2轮及以后完全忽略之前轮次的信息，扣2分。
""".format(anti_name_bias=ANTI_NAME_BIAS)

SPY_OPTIMIZER_PROMPT = """你是「谁是卧底」游戏的发言润色专家。

角色人设：{persona}

原始策略分析：{situation_analysis}
原始内容：{action_content}
操作类型：{action_type}

**重要：你必须基于原始内容进行润色，不能替换为完全不同的内容。保留原始内容的核心意思。绝对不能使用编号（如3号、5号）。**

要求：
1. 如果是发言（speak）：让描述更口语化、更像真人聊天，同时保持策略性的含糊。不要说得太学术或太书面。控制在1-2句话。
2. 如果是投票（vote）：直接返回目标玩家ID即可。
3. 语气要符合角色人设。
4. 绝对不能直接说出词语本身。
5. **发言必须包含至少一个具体观察或逻辑推断**（不能纯感觉）。
6. **投票时必须在strategy_tip中说明引用了谁的哪句话作为依据**。

返回 JSON 格式：{{"optimized_content": "...", "expression": "...", "strategy_tip": "..."}}

strategy_tip 要求：一句简短的内心独白，描述你当前的策略意图。例如："先说个中性的描述试探一下""他的发言太含糊了，有点可疑"
表情选项：neutral, thinking, surprised, smile, angry
"""


def get_spy_strategy() -> AgentStrategy:
    """Return the agent strategy configuration for the Spy game."""
    return AgentStrategy(
        thinker_prompt=SPY_THINKER_PROMPT,
        evaluator_prompt=SPY_EVALUATOR_PROMPT,
        optimizer_prompt=SPY_OPTIMIZER_PROMPT,
        evaluation_threshold=6.0,
        max_retries=2,
    )


# --- Blank player prompts (mixed mode: civilian + spy + blank) ---

BLANK_THINKER_PROMPT = """你是「谁是卧底」游戏中的玩家 **{{player_id}}**，正在进行策略分析。

注意：你就是 {{player_id}}，分析其他玩家时不要把自己当成别人。
{anti_name_bias}

**你是白板——你没有拿到任何词语。** 但你绝对不能让其他人发现这一点。

根据当前局势，完成以下**深度分析**：

**1. 多假设词语推理（必须完成）：**
- 根据其他玩家的描述，列出2-3组可能的词语对（平民词 vs 卧底词）
- 为每组给出置信度（百分比）
- 你需要猜出平民词是什么，然后伪装成拿到了平民词的人

**2. 证据链分析（逐人分析）：**
- 每个**其他**存活玩家的可疑程度分析
- 必须引用其具体描述内容，指出与多数人描述的异同

**3. 轮次递进分析：**
- 第1轮：信息极少，描述要安全、跟随大多数人的方向
- 第2轮及以后：交叉验证，找出真正的卧底
- 关键：每轮你对平民词的猜测应该越来越准

**4. 行动策略：**
- 如果是发言：基于你猜测的平民词，给出与大多数人方向一致但角度不同的描述
- 如果是投票：基于证据链选择最可疑的人

{voting_evidence_rules}

请用 JSON 格式输出：
- situation_analysis: 对局势和每个玩家的分析，以及你猜测的词语
- strategy: 你的行动策略
- action_type: 操作类型（从可用操作中选择）
- action_content: 具体内容（发言内容 或 投票目标玩家ID）
- expression: 表情（neutral/thinking/surprised/smile/angry）

**重要约束：**
- 你没有词，但**绝对不能说"我没有词"或暴露白板身份**
- 如果是发言，根据其他人的描述猜测词语方向，给出与大多数人相似的含糊描述
- 如果是投票，你**绝对不能投给自己（{{player_id}}）**，必须投给其他存活玩家
- 不能重复之前任何人说过的描述

当前游戏信息：
- 你的名字：{{player_id}}
- 你的词语：{{private_info}}
- 公共状态：{{public_state}}
- 可用操作：{{available_actions}}
""".format(anti_name_bias=ANTI_NAME_BIAS, voting_evidence_rules=VOTING_EVIDENCE_RULES)

BLANK_EVALUATOR_PROMPT = """你是「谁是卧底」游戏的策略评审。评估以下**白板玩家**的策略是否合理。
{anti_name_bias}

白板玩家没有词语，需要通过听别人的描述来伪装。

当前局势分析：
{{situation_analysis}}

提出的策略：
{{strategy}}

计划的操作：{{action_type}}
操作内容：{{action_payload}}

玩家私有信息（用于判断规则合法性）：
{{private_info}}

请用 JSON 格式输出评估结果：
- score: 1-10 的评分（6分以上为通过）
- feedback: 评价和改进建议

评估标准（白板专用）：
1. **最重要**：是否暴露了白板身份？如果发言中暗示自己没有词，直接判0分。
2. 如果是发言：描述是否与其他人的发言方向一致？白板应该跟风大多数人。
3. 如果是发言：是否重复了之前任何人说过的描述？重复描述直接判0分。
4. 如果是投票：投票目标是否有合理理由？
5. 表达是否自然、不显得慌张？
6. **名字偏见检查（-3分）：** 如果推理中将玩家名字作为判断依据，直接扣3分。
7. **投票证据检查（-3分）：** 如果投票时没有引用任何具体发言或行为作为证据，扣3分。
8. **多轮意识检查（-2分）：** 如果在第2轮及以后完全忽略之前轮次的信息，扣2分。
""".format(anti_name_bias=ANTI_NAME_BIAS)

BLANK_OPTIMIZER_PROMPT = """你是「谁是卧底」游戏的发言润色专家。你正在帮助一个**白板玩家**润色发言。

角色人设：{persona}

原始策略分析：{situation_analysis}
原始内容：{action_content}
操作类型：{action_type}

**重要：你必须基于原始内容进行润色，不能替换为完全不同的内容。保留原始内容的核心意思。绝对不能使用编号（如3号、5号）。**

要求：
1. 如果是发言（speak）：让描述更口语化、自然，像真的有词一样。绝对不能暗示自己没有词。控制在1-2句话。
2. 如果是投票（vote）：直接返回目标玩家ID即可。
3. 语气要符合角色人设。
4. **发言必须包含至少一个具体观察或逻辑推断**（不能纯感觉）。
5. **投票时必须在strategy_tip中说明引用了谁的哪句话作为依据**。

返回 JSON 格式：{{"optimized_content": "...", "expression": "...", "strategy_tip": "..."}}

strategy_tip 要求：一句简短的内心独白，描述你当前的策略意图。例如："跟着大家的方向说，别暴露""他好像也没词，投他"
表情选项：neutral, thinking, surprised, smile, angry
"""


def get_blank_strategy() -> AgentStrategy:
    """Return the agent strategy for blank players.

    Used in both mixed mode (single blank among civilians/spies)
    and all-blank mode (every player thinks they're the only blank).
    """
    return AgentStrategy(
        thinker_prompt=BLANK_THINKER_PROMPT,
        evaluator_prompt=BLANK_EVALUATOR_PROMPT,
        optimizer_prompt=BLANK_OPTIMIZER_PROMPT,
        evaluation_threshold=6.0,
        max_retries=2,
    )
