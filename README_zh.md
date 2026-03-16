# Masquerade

**AI 桌游竞技场** — 大模型 Agent 自主进行社交推理博弈，拥有独立的推理、记忆和策略。完整对局可生成电影级视频或网页交互回放。

[English](README.md)

https://github.com/GOODDAYDAY/Masquerade

---

## 这是什么？

Masquerade 是一个全自动的 AI 桌游对局系统。每个玩家都是独立的大模型 Agent，拥有自己的人格、记忆和决策策略。整场游戏 —— 思考、发言、投票、欺骗、结盟 —— **全部由 AI 自主完成，零人类干预**。

对局结束后，Masquerade 可以：
- **网页交互回放** — 带播放控制和语音的剧场式回放
- **渲染为视频** — 2K 60fps MP4，TTS 配音，音画完美同步（Remotion 逐帧渲染）

### 支持的游戏

| 游戏 | 人数 | 说明 |
|:-----|:-----|:-----|
| **谁是卧底** | 3–8 人 | 每人获得一个秘密词语，卧底的词语不同。通过讨论和投票找出卧底。 |
| **狼人杀** | 8–12 人 | 经典社交推理游戏，6 种角色：狼人、村民、预言家、女巫、猎人、守卫。包含完整的昼夜阶段和角色技能。 |

## 架构

```
┌──────────────────────────────────────────────────┐
│              Masquerade 完整流程                    │
│                                                  │
│  1. 游戏模拟     Python 后端                       │
│     GameEngine ←→ PlayerAgent (LLM)              │
│     Orchestrator 驱动回合，录制脚本                  │
│                                                  │
│  2. TTS 生成     edge-tts                        │
│     脚本 → 每条发言生成 MP3 音频                     │
│                                                  │
│  3. 输出                                          │
│     ├─ 网页交互剧场 (React + Vite)                 │
│     └─ 视频渲染 (Remotion, 2K 60fps)              │
└──────────────────────────────────────────────────┘
```

### 核心设计理念

- **游戏引擎** — 纯游戏逻辑，与 LLM 解耦。轻松扩展新游戏。
- **智能体** — 基于 LangGraph 的推理框架，具备记忆、策略提示和表情追踪。
- **编排器** — 引擎与智能体解耦。批量阶段（投票、夜间行动）支持并发 LLM 调用。
- **脚本** — 结构化 JSON 输出，包含完整时间线、内心独白、记忆快照。
- **前端** — 游戏无关的 React 组件。一套 UI 支持所有游戏类型。
- **Remotion** — 确定性帧驱动渲染。相同输入永远产生相同输出。

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- OpenAI 兼容的 LLM API Key（DeepSeek、OpenAI 等）
- ffmpeg（视频渲染需要）

### 安装

```bash
# 克隆项目
git clone https://github.com/GOODDAYDAY/Masquerade.git
cd Masquerade

# Python 依赖
pip install -e .

# 前端依赖
cd frontend && npm install && cd ..

# 配置 LLM API Key
cp .env.example .env
# 编辑 .env，设置 MASQUERADE_LLM__API_KEY
```

### 运行游戏

```bash
# 查看可用游戏
python -m backend.main --list

# 运行谁是卧底
python -m backend.main spy

# 运行狼人杀
python -m backend.main werewolf
```

输出：`output/scripts/game_<类型>_<时间戳>.json`

### 生成 TTS 音频

```bash
python -m backend.tts.generate output/scripts/game_spy_xxx.json
```

输出：`output/audio/<game_id>/`（MP3 文件 + manifest.json）

### 网页交互回放

```bash
cd frontend && npm run dev
```

打开 `http://localhost:5173`，拖入游戏脚本 JSON，即可观看带播放控制和语音的交互式回放。

### 渲染视频 (Remotion)

```bash
# 将指定游戏脚本渲染为 MP4
node scripts/render-video.mjs game_spy_xxx.json
```

输出：`output/videos/<游戏名>.mp4`（2K 60fps，H.264）

### 一键完整流程

```bash
# Windows: 运行游戏 → 生成 TTS → 渲染视频
scripts\run.bat
```

## 项目结构

```
Masquerade/
├── backend/
│   ├── main.py              # CLI 入口
│   ├── engine/              # 游戏引擎（谁是卧底、狼人杀）
│   ├── agent/               # LLM 玩家智能体（LangGraph）
│   ├── orchestrator/        # 游戏编排器 + 并发控制
│   ├── script/              # 脚本录制（JSON 输出）
│   ├── tts/                 # TTS 音频生成（edge-tts）
│   └── core/                # 配置、日志、异常
├── frontend/
│   ├── src/
│   │   ├── components/      # 交互式剧场（React + Framer Motion）
│   │   ├── remotion/        # 视频渲染（Remotion，帧驱动）
│   │   ├── core/            # 时间轴控制器、音频管理器
│   │   └── types/           # 共享 TypeScript 类型
│   └── package.json
├── config/
│   ├── app_config.yaml      # 全局设置（LLM、并发、日志）
│   └── games/               # 游戏配置（玩家、角色、词语）
├── scripts/                  # 自动化脚本（.bat + .sh）
├── output/                   # 生成的脚本、音频、视频
└── requirements/             # 需求跟踪文档
```

## 配置

### LLM 提供商

Masquerade 支持任何 **OpenAI 兼容 API**。在 `.env` 或 `config/app_config.yaml` 中配置：

```yaml
llm:
  model: deepseek-chat
  api_base: https://api.deepseek.com/v1
  temperature: 0.7
```

已测试：**DeepSeek**、**OpenAI**、**本地大模型**（通过 ollama/vLLM）。

### 游戏配置

在 `config/games/` 中自定义玩家、角色和规则：

```yaml
# config/games/spy.yaml
spy_count: 1
blank_count: 0
players:
  - name: 小明
    persona: "谨慎的分析师，先观察再发言"
  - name: 小红
    persona: "大胆的领导者，主导讨论方向"
  # ...
```

## 扩展

### 添加新游戏

1. 创建 `backend/engine/<游戏>/game.py`，继承 `GameEngine`
2. 在 `strategy.py` 中定义角色特定策略
3. 用 `@register_game("game_name")` 注册
4. 在 `config/games/<游戏>.yaml` 添加配置
5. 前端场景组件是游戏无关的 —— 新游戏自动适配

### 更换 TTS 引擎

替换 `backend/tts/generate.py` 即可。接口约定：每个游戏脚本产出 MP3 文件 + `manifest.json`。

## 技术栈

| 层级 | 技术 |
|:-----|:-----|
| 游戏引擎 | Python, Pydantic |
| LLM 智能体 | LangGraph, OpenAI SDK |
| 语音合成 | edge-tts（微软，免费） |
| 交互式回放 | React 18, TypeScript, Framer Motion, Tailwind CSS, Vite |
| 视频渲染 | Remotion 4（帧驱动，确定性） |
| 视频编码 | H.264 via ffmpeg，GPU 加速（NVENC/AMF/QSV 自动检测） |

## 许可证

[Apache License 2.0](LICENSE) — 可自由使用、修改和分发，需保留出处声明。
