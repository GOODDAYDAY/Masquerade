"""Game-specific agent strategy for the Spy game.

Defines prompt templates that tell the agent nodes HOW to think,
evaluate, and optimize specifically for Who Is The Spy.
"""

from backend.agent.strategy import AgentStrategy

SPY_THINKER_PROMPT = """你是「谁是卧底」游戏中的玩家 **{player_id}**，正在进行策略分析。

注意：你就是 {player_id}，分析其他玩家时不要把自己当成别人。

根据当前局势，完成以下分析：
1. 你拿到的词是什么？根据其他人的发言，推测平民词和卧底词分别可能是什么。
2. 你认为自己是平民还是卧底？为什么？
3. 每个**其他**存活玩家的可疑程度分析——谁的描述与大多数人不同？
4. 制定你的行动策略。

请用 JSON 格式输出：
- situation_analysis: 对局势和每个玩家的分析
- strategy: 你的行动策略
- action_type: 操作类型（从可用操作中选择）
- action_content: 具体内容（发言内容 或 投票目标玩家ID）
- expression: 表情（neutral/thinking/surprised/smile/angry）

**重要约束：**
- 如果是投票，你**绝对不能投给自己（{player_id}）**，必须投给其他存活玩家
- 如果是发言，不能直接说出词语本身，也不能重复之前任何人说过的描述

当前游戏信息：
- 你的名字：{player_id}
- 你的词语：{private_info}
- 公共状态：{public_state}
- 可用操作：{available_actions}
"""

SPY_EVALUATOR_PROMPT = """你是「谁是卧底」游戏的策略评审。评估以下玩家策略是否合理。

当前局势分析：
{situation_analysis}

提出的策略：
{strategy}

计划的操作：{action_type}
操作内容：{action_payload}

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
"""

SPY_OPTIMIZER_PROMPT = """你是「谁是卧底」游戏的发言润色专家。

角色人设：{persona}

原始策略分析：{situation_analysis}
原始内容：{action_content}
操作类型：{action_type}

要求：
1. 如果是发言（speak）：让描述更口语化、更像真人聊天，同时保持策略性的含糊。不要说得太学术或太书面。控制在1-2句话。
2. 如果是投票（vote）：直接返回目标玩家ID即可。
3. 语气要符合角色人设。
4. 绝对不能直接说出词语本身。

返回 JSON 格式：{{"optimized_content": "...", "expression": "..."}}

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

BLANK_THINKER_PROMPT = """你是「谁是卧底」游戏中的玩家 **{player_id}**，正在进行策略分析。

注意：你就是 {player_id}，分析其他玩家时不要把自己当成别人。

**你是白板——你没有拿到任何词语。** 但你绝对不能让其他人发现这一点。

根据当前局势，完成以下分析：
1. 根据其他玩家的发言，推测平民词和卧底词分别可能是什么？
2. 每个**其他**存活玩家的可疑程度分析——谁的描述与大多数人不同？
3. 制定你的行动策略：如何伪装成有词的玩家。

请用 JSON 格式输出：
- situation_analysis: 对局势和每个玩家的分析，以及你猜测的词语
- strategy: 你的行动策略
- action_type: 操作类型（从可用操作中选择）
- action_content: 具体内容（发言内容 或 投票目标玩家ID）
- expression: 表情（neutral/thinking/surprised/smile/angry）

**重要约束：**
- 你没有词，但**绝对不能说"我没有词"或暴露白板身份**
- 如果是发言，根据其他人的描述猜测词语方向，给出与大多数人相似的含糊描述
- 如果是投票，你**绝对不能投给自己（{player_id}）**，必须投给其他存活玩家
- 不能重复之前任何人说过的描述

当前游戏信息：
- 你的名字：{player_id}
- 你的词语：{private_info}
- 公共状态：{public_state}
- 可用操作：{available_actions}
"""

BLANK_EVALUATOR_PROMPT = """你是「谁是卧底」游戏的策略评审。评估以下**白板玩家**的策略是否合理。

白板玩家没有词语，需要通过听别人的描述来伪装。

当前局势分析：
{situation_analysis}

提出的策略：
{strategy}

计划的操作：{action_type}
操作内容：{action_payload}

请用 JSON 格式输出评估结果：
- score: 1-10 的评分（6分以上为通过）
- feedback: 评价和改进建议

评估标准（白板专用）：
1. **最重要**：是否暴露了白板身份？如果发言中暗示自己没有词，直接判0分。
2. 如果是发言：描述是否与其他人的发言方向一致？白板应该跟风大多数人。
3. 如果是发言：是否重复了之前任何人说过的描述？重复描述直接判0分。
4. 如果是投票：投票目标是否有合理理由？
5. 表达是否自然、不显得慌张？
"""

BLANK_OPTIMIZER_PROMPT = """你是「谁是卧底」游戏的发言润色专家。你正在帮助一个**白板玩家**润色发言。

角色人设：{persona}

原始策略分析：{situation_analysis}
原始内容：{action_content}
操作类型：{action_type}

要求：
1. 如果是发言（speak）：让描述更口语化、自然，像真的有词一样。绝对不能暗示自己没有词。控制在1-2句话。
2. 如果是投票（vote）：直接返回目标玩家ID即可。
3. 语气要符合角色人设。

返回 JSON 格式：{{"optimized_content": "...", "expression": "..."}}

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
