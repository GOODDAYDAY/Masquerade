"""Game-specific agent strategy for the Spy game.

Defines prompt templates that tell the agent nodes HOW to think,
evaluate, and optimize specifically for Who Is The Spy.
"""

from backend.agent.strategy import AgentStrategy

SPY_THINKER_PROMPT = """你是「谁是卧底」游戏中的一名玩家，正在进行策略分析。

根据当前局势，完成以下分析：
1. 你拿到的词是什么？根据其他人的发言，推测平民词和卧底词分别可能是什么。
2. 你认为自己是平民还是卧底？为什么？
3. 每个存活玩家的可疑程度分析——谁的描述与大多数人不同？
4. 制定你的行动策略。

请用 JSON 格式输出：
- situation_analysis: 对局势和每个玩家的分析
- strategy: 你的行动策略
- action_type: 操作类型（从可用操作中选择）
- action_content: 具体内容（发言内容 或 投票目标玩家ID）
- expression: 表情（neutral/thinking/surprised/smile/angry）

当前游戏信息：
- 你的身份信息：{private_info}
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
2. 如果是投票：投票目标是否有充分的可疑理由？不能乱投。
3. 如果玩家可能是卧底：策略是否在伪装？还是在暴露自己？
4. 表达是否自然、像真人在玩游戏？
5. 是否有考虑到之前轮次的信息？
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
