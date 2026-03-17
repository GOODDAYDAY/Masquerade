# REQ-015: Gameplay Quality Fixes — Anti-Hallucination & Logic Improvements

## 1. Background

Analysis of game_werewolf_20260317_091505.json revealed multiple gameplay quality issues.

## 2. Issues & Fixes

### Issue 1: Optimizer generates hallucinated content (CRITICAL)
**Symptom:** First speaker in Round 1 says "我注意到甄逻辑的发言有矛盾" — but nobody has spoken yet. Thinker correctly identified "目前尚未听到任何人发言" but the optimizer fabricated references to non-existent speeches.

**Root cause:** Optimizer doesn't receive the constraint that it must NOT invent facts not present in the original analysis. It "creatively" adds specific references that don't exist.

**Fix:** Add anti-hallucination constraint to ALL optimizer prompts:
```
**反幻觉规则（严格执行）：**
你只能基于原始策略分析中提到的事实进行润色。绝对不能：
- 编造其他玩家没说过的话（如"xxx刚才说了..."，但原始分析里没提到）
- 引用不存在的发言或行为
- 添加原始分析中没有的具体细节
如果原始分析表明"暂无信息"，润色后也不能凭空引用信息。
```

### Issue 2: Seer reports inconsistent check result
**Symptom:** Seer's thinking says "查验甄推理是狼人", but speech says a different player name.

**Root cause:** Optimizer changes the target name during "creative" polishing. Same hallucination category — optimizer invents/changes facts.

**Fix:** Covered by Issue 1's anti-hallucination constraint. Additionally add:
```
如果原始内容涉及查验结果、投票目标等关键信息，润色时必须保持一致，不能更改具体的玩家名字或结论。
```

### Issue 3: Witch always saves on first night without analysis
**Symptom:** Witch immediately uses antidote on first night regardless of circumstances.

**Root cause:** Witch prompt says "第一晚大概率值得救" too strongly. AI interprets this as "always save first night."

**Fix:** Revise witch night thinker prompt to require case-by-case analysis:
```
**解药决策（必须逐项分析，不要默认救人）：**
1. 今晚被杀的是谁？
2. 这个人白天的发言质量如何？（第一晚无发言信息，无法判断）
3. 是否有狼人自刀嫌疑？
4. 如果第一晚且无任何信息：你可以选择救，也可以选择留药。留药的价值是后续轮次有更多信息时能做出更好的判断。不要无脑救。
```

### Issue 4: wolf_discuss skips LLM evaluation (evaluator bug)
**Symptom:** Log shows "Evaluator: programmatic validation PASSED, skipping LLM (target-only action)" for wolf_discuss. But wolf_discuss has gesture text content that should be quality-checked.

**Root cause:** Evaluator's `_is_target_only_action()` check incorrectly classifies wolf_discuss as target-only because the tools_schema's primary field is "gesture" (not "content"/"target").

**Fix:** In evaluator.py, change the target-only detection to NOT skip LLM for wolf_discuss. The check should look at whether action_content is a short target ID vs longer text.

### Issue 5: wolf_discuss gestures contain "表示xxx" descriptions (equivalent to speech)
**Symptom:** Gestures like "微微点头表示这是我的首选" — "表示" is basically narration, not a gesture.

**Fix:** Add to wolf night evaluator:
```
不能出现"表示""意味着""暗示"等解释性文字。动作描述应该是纯动作：
✅ "用食指指向甄逻辑，微微点头"
❌ "用食指指向甄逻辑，表示这是首选目标"
```

### Issue 6: First speaker has no information but must speak substantively
**Symptom:** Round 1 first speaker fabricates analysis because they have nothing real to analyze.

**Fix:** Add round-awareness to optimizer prompts:
```
如果这是本轮第一个发言且没有可引用的其他玩家发言，你的发言应该：
- 提出自己的观察框架（"我们先从xxx角度分析"）
- 表达自己的立场（"我认为我们应该关注xxx"）
- 不要引用任何其他玩家的"发言"，因为还没人说话
```

### Issue 7: Gesture descriptions too long and template-like
**Symptom:** Every wolf gesture is 3-4 sentences, all follow the same pattern "抬起右手→食指指向→保持两秒→点头→收回手→再指..."

**Fix:** Wolf night optimizer prompt add:
```
手势描述要简短自然，1-2个动作即可，不要写成动作说明书。
✅ "坚定地指向甄逻辑，然后看向队友微微点头"
❌ "首先缓慢抬起右手，用食指指向甄逻辑，保持指向姿势约两秒，眼神平静地看向队友，微微点头表示这是我的首选"
```

## 3. Files to Modify

| File | Changes |
|------|---------|
| `backend/engine/werewolf/strategy.py` | All optimizer prompts: anti-hallucination. Wolf night: gesture constraints. Witch: revised save logic. |
| `backend/engine/spy/strategy.py` | All optimizer prompts: anti-hallucination. |
| `backend/engine/shared_prompts.py` | Add ANTI_HALLUCINATION shared fragment |
| `backend/agent/nodes/evaluator.py` | Fix wolf_discuss LLM skip bug |

## 4. Acceptance Criteria

- [ ] AC-1: First speaker in Round 1 does NOT reference other players' speeches
- [ ] AC-2: Seer's reported check result matches their actual check
- [ ] AC-3: wolf_discuss goes through LLM evaluation (not skipped)
- [ ] AC-4: Wolf gestures don't contain "表示"/"意味着" narration
- [ ] AC-5: Wolf gestures are 1-2 actions, not 3-4 sentence templates
- [ ] AC-6: Witch first-night decision includes analysis, not auto-save

## 5. Change Log

| Version | Date | Changes | Affected Scope | Reason |
|:---|:---|:---|:---|:---|
| v1 | 2026-03-17 | Initial version | ALL | - |
