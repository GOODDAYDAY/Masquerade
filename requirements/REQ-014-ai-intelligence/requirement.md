# REQ-014: AI Intelligence & Prompt Quality Upgrade

## 1. Background & Motivation

Based on analysis of historical game scripts and the current prompt/config system, several intelligence issues have been identified:

### Problem 1: Name Bias in Voting ("逮着甄狂妄投")
AI agents use character names as voting evidence. A player named "甄狂妄" (arrogant) gets targeted simply because the name implies arrogance, not because of actual in-game behavior. Names are for audience entertainment only — they should not influence AI decision-making.

### Problem 2: Shallow Voting Logic
Current spy thinker prompt only constrains "cannot vote self." There is no structured requirement to:
- Cite specific speech evidence before voting
- Compare suspicion levels across all players
- Distinguish between "personality I don't like" vs "behavior inconsistent with role"

### Problem 3: Thin Personas
Spy game personas are single-sentence descriptions. This produces generic AI behavior — all agents sound similar after the optimizer polishes their speech. Richer personas with behavioral patterns, speech habits, and decision-making tendencies would create more diverse and entertaining gameplay.

### Problem 4: Insufficient Strategic Depth
- Thinker lacks multi-hypothesis reasoning ("What if I'm wrong about who the spy is?")
- No evidence-weight scoring across rounds
- Evaluator doesn't penalize evidence-free voting
- Spy agents don't adapt strategy based on what descriptions have been used

### Problem 5: Werewolf Prompt Gaps
- Wolf night discussion gestures are too generic
- Seer jump timing is inconsistent
- Villagers default to passive observation instead of active deduction
- Guard protection logic doesn't adapt across rounds

## 2. Goals

1. Eliminate name-based bias — AI must judge by behavior, not names
2. Upgrade all game prompts for deeper strategic reasoning
3. Enrich persona definitions in spy.yaml and werewolf.yaml
4. Improve voting logic with evidence requirements
5. Enhance multi-round memory utilization in decisions

## 3. Scope

### In Scope
- FR-1: Anti-name-bias prompt injection (all games)
- FR-2: Spy game prompt overhaul (thinker, evaluator, optimizer)
- FR-3: Werewolf game prompt overhaul (all roles, day/night)
- FR-4: Persona enrichment (spy.yaml, werewolf.yaml)
- FR-5: Voting evidence requirements (spy + werewolf)

### Out of Scope
- Agent architecture changes (LangGraph node structure stays the same)
- New game types
- Temperature/retry parameter tuning
- Frontend/video changes

## 4. Functional Requirements

### FR-1: Anti-Name-Bias System Prompt

Add a universal constraint to ALL thinker and evaluator prompts across all games:

```
重要规则：玩家的名字（如"甄狂妄""甄怂包"等）只是角色外号，用于观众识别。
你在分析、推理、投票时，必须完全基于玩家的【实际发言内容】【行为模式】【逻辑一致性】做判断。
绝对不能因为一个人的名字听起来"狂妄""阴险""老实"就对其产生正面或负面偏见。
名字 ≠ 行为证据。
```

**Placement:** In every thinker prompt's constraint section, and in evaluator prompts as a scoring criterion ("Did the AI cite name-based reasoning? If so, -3 points").

### FR-2: Spy Game Prompt Overhaul

#### FR-2.1: Spy Thinker Prompt Enhancement
Current prompt asks for basic analysis. Upgrade to require:

1. **Multi-hypothesis reasoning:**
   - "List 2-3 possible word pairs that fit the descriptions so far"
   - "For each hypothesis, which players' descriptions are consistent/inconsistent?"
   - "What is my confidence level (high/medium/low) for each hypothesis?"

2. **Evidence-chain voting:**
   - "Before voting, list the specific speech evidence against your target"
   - "Compare your target vs other candidates — why is this person MORE suspicious?"
   - "Consider: could this person be bluffing? What would a bluff look like?"

3. **Adaptive description strategy (for spy):**
   - "What descriptions have already been used? Don't overlap."
   - "What aspects of your word can bridge to the civilian word?"
   - "Which description angle would make you blend in best given what's been said?"

4. **Round-progressive analysis:**
   - Round 1: "Focus on gathering info, describe conservatively"
   - Round 2+: "Cross-reference all prior descriptions, identify inconsistencies"
   - Final rounds: "High-confidence deduction required, cite specific evidence"

#### FR-2.2: Spy Evaluator Prompt Enhancement
Add scoring criteria:
- **Evidence-based voting (new, weight: 3 points):** Did the player cite specific speech content as voting reason? Generic "I feel like X is suspicious" = -3 points.
- **Name bias check (new, weight: 3 points):** Did reasoning reference player names as evidence? "甄狂妄 seems arrogant so probably spy" = -3 points.
- **Multi-round awareness (upgrade, weight: 2 points):** Did analysis reference prior round events? First-round-only thinking in round 3 = -2 points.

#### FR-2.3: Spy Optimizer Prompt Enhancement
Add constraints:
- "Speech must contain at least one concrete observation or logical deduction, not just vague feelings"
- "Voting justification must reference specific speech content from other players"
- "Maintain persona voice but ensure substance over style"

### FR-3: Werewolf Game Prompt Overhaul

#### FR-3.1: Wolf Night Enhancement
- **Silent action constraint (critical):** All night-phase gestures must be completely silent. Only hand signals, eye contact, pointing, nodding, head-shaking allowed. Absolutely NO sound-producing actions: no table-slapping, hand-clapping, foot-stomping, finger-snapping, or any physical contact with objects. Evaluator must score 0 if any sound-producing action is described.
- Add explicit teammate communication protocol: "First gesture = preferred target, second gesture = agreement/disagreement with partner"
- Add guard-prediction depth: "Think about what the guard THINKS you'll do, then do the opposite of the opposite"
- Add witch-awareness: "If witch saved last night's target, try a different approach"

#### FR-3.2: Seer Day Enhancement
- Clearer jump timing logic: "If you found a wolf, jump immediately. Silence helps wolves."
- Counter-seer protocol: "If someone else claims seer, you MUST counter-claim with your verification chain"
- Gold-chain presentation: "Present verifications chronologically with reasoning"

#### FR-3.3: Witch Night Enhancement
- Stronger poison-usage encouragement: "Sitting on poison while wolves kill every night is losing strategy. 60% confidence = use it."
- First-night save guidance: "First night, save unless strong evidence of wolf self-stab"
- Information synthesis: "Use day-phase discussion to inform night decisions"

#### FR-3.4: Guard Night Enhancement
- Multi-level meta-game in protection: "Don't just think about who wolves target — think about who wolves think YOU'LL protect, and protect someone else"
- Exposed-role priority: "Confirmed seer/witch = highest protection priority"
- Self-protect awareness: "If you're outed as guard, self-protect is valid"

#### FR-3.5: Villager Day Enhancement
- Active deduction framework: "Analyze voting patterns — who always follows who? Who switches votes last-minute?"
- Speech analysis guide: "Wolf speech patterns: hollow praise of others, vague accusations, bandwagon voting"
- Team consolidation: "Good team loses when votes scatter. Identify consensus target and commit."

#### FR-3.6: Hunter Death Enhancement
- Shoot-priority: "Seer-identified wolf > most-suspected by voting pattern > silent observer"
- Anti-skip emphasis: "NOT shooting is almost always wrong. Better to guess than waste your skill."

### FR-4: Persona Enrichment

#### FR-4.1: Spy Game Personas (spy.yaml)

Expand each persona from one sentence to a structured profile:

```yaml
players:
  - name: 甄大胆
    persona: >
      性格直爽，永远第一个发言，不怕暴露。
      说话风格：短句为主，语气果断，常用反问句。
      决策方式：直觉优先，看到可疑马上点名质疑。
      弱点：容易打草惊蛇，情绪上来会暴露更多信息。
    appearance: 短发，皮肤黝黑，声音洪亮
```

Each persona should include:
- **性格特点** (personality traits)
- **说话风格** (speech patterns — sentence length, common expressions, tone)
- **决策方式** (decision-making style — intuitive vs analytical, aggressive vs cautious)
- **弱点** (weakness — what makes them exploitable or predictable)

#### FR-4.2: Werewolf Game Personas (werewolf.yaml)

Same expansion for all 12 players. Each persona should be 3-5 lines covering the four dimensions above.

### FR-5: Voting Evidence Requirements

Add to ALL voting-related prompts (spy + werewolf day phase):

```
投票规则（强制）：
1. 投票前必须列出至少一条具体证据（引用某人的原话或具体行为）
2. 证据必须来自游戏内发言，不能来自玩家名字或第一印象
3. 必须解释为什么这条证据指向你的投票目标
4. 如果没有明确证据，必须说明是基于消去法还是概率判断
```

## 5. Acceptance Criteria

- [ ] AC-1: Run 3 spy games — no voting decision references player names as evidence
- [ ] AC-2: Run 3 spy games — every vote includes at least one specific speech citation
- [ ] AC-3: Spy personas are multi-line structured profiles (4 dimensions each)
- [ ] AC-4: Werewolf personas are multi-line structured profiles (4 dimensions each)
- [ ] AC-5: All thinker prompts include anti-name-bias constraint
- [ ] AC-6: All evaluator prompts penalize name-based reasoning
- [ ] AC-7: Spy thinker prompt includes multi-hypothesis reasoning section
- [ ] AC-8: Werewolf role prompts updated per FR-3 specifications
- [ ] AC-9: Existing tests still pass (prompt changes don't break action format)

## 6. Change Log

| Version | Date | Changes | Affected Scope | Reason |
|:---|:---|:---|:---|:---|
| v1 | 2026-03-16 | Initial version | ALL | - |
