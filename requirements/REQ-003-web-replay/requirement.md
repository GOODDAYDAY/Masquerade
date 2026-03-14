# REQ-003 Web Script Replay — Game Theater

> Status: Requirement Finalized
> Created: 2026-03-14
> Updated: 2026-03-14

## 1. Background

Masquerade 已经能产出完整的游戏剧本 JSON（含玩家信息、每轮发言、投票、思考过程、表情等）。现在需要一个 Web 前端回放器，将 JSON 剧本以"剧场"形式精细呈现，让观众像在看一场桌游直播，有铺有垫、有悬念有高潮。

同时需要一个 Python 脚本，利用 edge-tts 为每段发言预生成 MP3 音频，实现语音回放。

## 2. Target Users & Scenarios

- **内容消费者**：观看 AI 桌游对弈的完整过程，感受策略博弈和角色互动
- **开发者（自己）**：验证游戏质量、调试 prompt 效果

## 3. Functional Requirements

### F-01 TTS Audio Pre-generation Script

Python 脚本，将剧本 JSON 中所有发言转为 MP3 音频文件。

- Main flow:
  - 输入：`output/scripts/game_spy_*.json`
  - 输出：`output/audio/<game_id>/` 目录下的 MP3 文件
  - 为每个发言事件生成一个 MP3：`<round>_<event_index>_<player_id>.mp3`
  - 使用 edge-tts（免费、中文支持好）
  - 不同玩家使用不同声线（edge-tts 支持多种中文声线）
  - 可在 game_config.yaml 的玩家配置中指定声线，或自动分配
  - 脚本入口：`python -m backend.tts.generate <script_json_path>`
  - 生成完毕后输出音频目录路径和文件清单
- Error handling:
  - edge-tts 未安装时提示安装命令
  - 单条发言生成失败不中断，跳过并记录错误
- Edge cases:
  - 投票事件不生成音频（只有 speak 类型生成）

### F-02 Game Theater — Opening Scene

开场介绍，建立氛围。

- Main flow:
  - 显示游戏标题"谁是卧底"+ 游戏创建时间
  - 逐个展示玩家卡片（头像 + 名字 + 性格描述 + 外貌描述）
  - 头像：使用 appearance 描述中的特征生成简约风格 avatar（CSS/SVG 实现，如首字母头像 + 对应颜色）
  - 展示词对信息：平民词 "???" / 卧底词 "???"（剧透模式可提前揭晓）
  - 背景：深色主题（类似电影院），适当的入场动画
- Error handling: N/A
- Edge cases: 如果有背景音乐 MP3 放在 `assets/bgm/` 下，自动循环播放

### F-03 Game Theater — Speaking Phase

发言阶段的回放。

- Main flow:
  - 轮次标题动画："第 X 轮 · 发言阶段"
  - 当前发言玩家高亮，其他玩家变暗
  - 发言气泡以打字机效果逐字出现（配合 TTS 音频播放节奏）
  - 气泡样式区分不同玩家（颜色、位置）
  - 玩家表情变化（根据 expression 字段：neutral/thinking/surprised/smile/angry）
  - "导演评论"模式（可选）：显示玩家的 thinking 内心独白，半透明叠加在画面上
  - 发言间有适当停顿（可自动或手动控制）
- Error handling:
  - 如果音频文件不存在，静默跳过，仅显示文字
- Edge cases:
  - 思考时间较长时（thinking_duration_ms > 10s），显示"思考中..."的加载动画

### F-04 Game Theater — Voting Phase

投票阶段的回放，核心是悬念感。

- Main flow:
  - 轮次标题："第 X 轮 · 投票阶段"
  - 所有玩家头像排列，显示"投票中..."
  - 逐个揭晓投票结果（每个玩家的票指向谁），用连线动画
  - 票数统计动画（数字递增）
  - 结果宣布：
    - 有人被淘汰：戏剧性的淘汰动画（头像变灰 + 淘汰标记 + 音效）
    - 平票：显示"平票——无人淘汰"
- Error handling: N/A
- Edge cases: N/A

### F-05 Game Theater — Finale

游戏结束的揭晓场景。

- Main flow:
  - "游戏结束"大标题动画
  - 揭晓卧底身份：卧底玩家头像高亮，显示"卧底！"标记
  - 揭晓词对：平民词 vs 卧底词
  - 胜负宣布：大字展示"平民阵营获胜"或"卧底获胜"
  - 游戏统计：总轮次、淘汰顺序、耗时
  - 可选：回顾关键时刻（最精彩的发言、最关键的投票）
- Error handling: N/A
- Edge cases: N/A

### F-06 Playback Controls

回放控制功能。

- Main flow:
  - 播放/暂停按钮
  - 速度控制：0.5x / 1x / 1.5x / 2x
  - 进度条：显示当前回放进度，可拖拽跳转到特定轮次
  - 轮次跳转：点击轮次列表直接跳到对应轮次
  - 音量控制：背景音乐 + 语音分别可调
  - 剧透模式开关：提前显示卧底身份和词对
  - 导演评论开关：显示/隐藏思考过程
- Error handling: N/A
- Edge cases: N/A

### F-07 Script Loader

加载剧本文件。

- Main flow:
  - 打开网页后，显示"选择剧本"页面
  - 支持拖拽上传 JSON 文件
  - 支持从 URL 参数指定剧本路径（`?script=path/to/game.json`）
  - 验证 JSON 格式是否为有效的 GameScript
  - 自动检测对应的音频目录是否存在
  - 加载成功后进入 Opening Scene
- Error handling:
  - 无效 JSON：显示错误提示
  - 音频目录不存在：提示"音频未生成，将以静音模式回放"
- Edge cases: N/A

## 4. Non-functional Requirements

- **技术栈**：React 18 + TypeScript + Tailwind CSS + Vite
- **无需后端**：纯静态前端，双击 `index.html` 或 `npm run dev` 即可使用
- **响应式布局**：适配桌面端（最小宽度 1024px），暂不考虑移动端
- **性能**：剧本 JSON 通常 < 1MB，无需分页或懒加载
- **浏览器兼容**：Chrome 90+ / Edge 90+
- **可维护性**：组件化开发，方便后续添加新游戏类型的回放

## 5. Out of Scope

- ~~AI 生成头像~~ — 使用 CSS/SVG 简约头像，后续独立需求
- ~~实时回放（WebSocket）~~ — 仅支持离线剧本回放
- ~~移动端适配~~ — 后续优化
- ~~多语言支持~~ — 当前仅中文

## 6. Acceptance Criteria

| ID | Feature | Condition | Expected Result |
|:---|:---|:---|:---|
| AC-01 | F-01 | 运行 TTS 脚本 | 为每段发言生成 MP3，不同玩家不同声线 |
| AC-02 | F-02 | 打开回放页面加载剧本 | 显示开场介绍，逐个展示玩家信息 |
| AC-03 | F-03 | 发言阶段回放 | 气泡打字机效果，配合 TTS 音频 |
| AC-04 | F-04 | 投票阶段回放 | 逐个揭晓投票，连线动画，淘汰效果 |
| AC-05 | F-05 | 游戏结束回放 | 揭晓卧底身份、词对、胜负 |
| AC-06 | F-06 | 点击播放控制 | 播放/暂停/变速/跳转/音量均可用 |
| AC-07 | F-07 | 拖拽上传 JSON | 验证格式，加载成功进入回放 |

## 7. Change Log

| Version | Date | Changes | Affected Scope | Reason |
|:---|:---|:---|:---|:---|
| v1 | 2026-03-14 | Initial version | ALL | - |
