# REQ-013 Technical Design

> Status: Completed
> Requirement: requirement.md
> Created: 2026-03-16
> Updated: 2026-03-16

## 1. Technology Stack

| Module | Technology | Rationale |
|:---|:---|:---|
| Video rendering engine | Remotion 4.x | Frame-driven React → MP4, deterministic output, built-in audio composition |
| Rendering runtime | @remotion/renderer (Node.js API) | Programmatic rendering with full control over props, output path, codec settings |
| Bundler (Remotion) | @remotion/bundler (webpack) | Remotion requires its own bundler separate from Vite; bundles Remotion entry for rendering |
| Animation | Remotion interpolate() / spring() | Replaces framer-motion; frame-synchronized, deterministic |
| Styling | Tailwind CSS 3.x | Same as existing Theater; configured via Remotion's webpack override |
| Audio | Remotion `<Audio>` + `<Sequence>` | Native audio composition, frame-accurate sync, no post-processing |
| Types | TypeScript 5.x | Shared with existing frontend |
| Render script | Node.js (.mjs) | Uses @remotion/renderer API directly, avoids CLI string-escaping issues on Windows |
| Automation | .bat / .sh | Wraps Node.js render script |

## 2. Design Principles

- **High cohesion, low coupling**: Remotion module is self-contained under `frontend/src/remotion/`, communicates with existing code only via shared types and pure display components
- **Reuse first**: Share `GameScript` types, `ExpressionIcon`, color/avatar utils; extract pure logic (color hash, text speed calc) into shared utils
- **Deterministic by design**: All timing derived from precomputed frame ranges, zero runtime randomness
- **Testability**: Timeline precomputation is a pure function (input → output), independently testable without Remotion rendering

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                   Render Pipeline                    │
│                                                     │
│  GameScript JSON ──┐                                │
│                    ├──→ TimelineBuilder ──→ SceneFrameRange[]  │
│  Audio Manifest ───┘        (pure fn)     + totalFrames       │
│                                                     │
│  SceneFrameRange[] ──→ Remotion <Video> Composition │
│                         ├─ <Sequence> per scene     │
│                         ├─ Scene components          │
│                         │   (frame-driven render)   │
│                         └─ <Audio> at speech frames  │
│                                                     │
│  @remotion/renderer ──→ MP4 (H.264, 1080p, 30fps)  │
└─────────────────────────────────────────────────────┘
```

See `tech-architecture.puml` for the component diagram.

## 4. Module Design

### 4.1 Timeline Builder (`remotion/timeline.ts`)

- **Responsibility**: Convert GameScript + audio durations into a flat list of `SceneFrameRange` with absolute frame positions. Single source of truth for all timing.
- **Public interface**:
  ```typescript
  function buildFrameTimeline(
    script: GameScript,
    audioDurations: Map<string, number>,  // key: "round_eventIdx_playerId", value: ms
    fps: number
  ): { scenes: SceneFrameRange[]; totalFrames: number }
  ```
- **Internal structure**:
  - `msToFrames(ms, fps)` — convert milliseconds to frame count, rounding up
  - Scene-specific duration calculators (opening, speaking, action, voting, finale)
  - Transition gap: 15 frames (500ms @ 30fps) between scenes
  - Strategy tip duration: `ceil(len / 15 * fps) + msToFrames(500, fps)`
  - Speaking duration: `tipFrames + max(audioFrames, textFrames) + msToFrames(800, fps)`
- **Reuse notes**: Pure function, no React dependency. Can be unit tested independently. Could potentially be shared with interactive Theater if needed later.

### 4.2 Video Composition (`remotion/Video.tsx`)

- **Responsibility**: Top-level Remotion `<Composition>` that reads props, builds timeline, and lays out `<Sequence>` blocks for each scene.
- **Public interface**:
  ```typescript
  interface VideoProps {
    scriptFile: string;   // e.g. "game_werewolf_20260316_120000.json"
  }
  ```
- **Internal structure**:
  1. Load GameScript from `staticFile(`scripts/${scriptFile}`)`
  2. Load audio manifest from `staticFile(`audio/${gameId}/manifest.json`)`
  3. Call `buildFrameTimeline()` to get scene list + totalFrames
  4. Render three-column layout (action history | main scene | speech history)
  5. Map each `SceneFrameRange` to a `<Sequence from={startFrame} durationInFrames={duration}>` wrapping the appropriate scene component
  6. Audio `<Sequence>` blocks placed at speaking scene phase-2 start frames
- **Reuse notes**: Uses shared types from `@/types/game-script`

### 4.3 Scene Components (`remotion/scenes/`)

- **Responsibility**: Render individual scene content driven by `useCurrentFrame()`. Each component receives scene data and computes visual state from the current frame offset within its sequence.
- **Public interface**: Each scene component:
  ```typescript
  interface SceneProps<T> {
    data: T;              // Scene-specific data
    durationInFrames: number;
    fps: number;
  }
  ```
- **Internal structure**:

  | Component | Frame Logic |
  |-----------|------------|
  | `OpeningScene` | Player cards fade in staggered: card[i] visible at `frame >= i * 9` (300ms intervals). Title appears at frame 0 with spring animation. |
  | `RoundTitle` | Fade in (frames 0-9), hold, fade out (last 9 frames). Phase label (day/night) with icon. |
  | `SpeakingScene` | Two phases: `frame < tipEndFrame` → strategy tip with typewriter; `frame >= tipEndFrame` → speech bubble + typewriter. Character index = `floor(frame * 15 / fps)`. |
  | `ActionScene` | Two phases similar to SpeakingScene. Text actions: typewriter. Target actions: card appears with spring, holds 3s. |
  | `VotingScene` | Vote[i] revealed at `frame >= i * 36` (1.2s intervals). Result card appears after all votes + 30 frames. Eliminated player highlight with red overlay. |
  | `FinaleScene` | Winner banner spring-in at frame 0. Stats staggered fade-in at frames 18, 24, 54, 72. Player cards layout with winner highlight. |

- **Reuse notes**: Scene components import `PlayerAvatar` (Remotion version), `ExpressionIcon` (shared), and `AnimatedText` (Remotion version).

### 4.4 Shared Remotion Components (`remotion/components/`)

- **Responsibility**: Frame-driven equivalents of existing shared components.

  **AnimatedText**: Typewriter effect driven by frame number.
  ```typescript
  interface AnimatedTextProps {
    text: string;
    startFrame: number;     // relative to parent Sequence
    charsPerSecond?: number; // default 15
  }
  // visibleChars = min(text.length, floor((frame - startFrame) * charsPerSecond / fps))
  ```

  **FadeTransition**: Wrapper that applies opacity fade in/out using `interpolate()`.
  ```typescript
  interface FadeTransitionProps {
    durationInFrames: number;
    fadeInFrames?: number;   // default 9 (300ms)
    fadeOutFrames?: number;  // default 9
    children: React.ReactNode;
  }
  ```

  **PlayerAvatarStatic**: Pure version of PlayerAvatar without framer-motion. Extracts color hash and rendering logic; applies opacity/grayscale via inline styles instead of `motion.div`.

- **Reuse notes**: `ExpressionIcon` is reused directly (no framer-motion). Color hash logic extracted to shared `utils/colors.ts` for both Theater and Remotion.

### 4.5 Audio Integration (`remotion/Video.tsx` + `<Audio>`)

- **Responsibility**: Place TTS audio clips at precise frame positions within the composition.
- **Internal structure**:
  - For each speaking scene with audio, compute `audioStartFrame = scene.startFrame + tipDurationFrames`
  - Render `<Sequence from={audioStartFrame}><Audio src={staticFile(audioPath)} /></Sequence>`
  - Audio file paths from manifest: `audio/{gameId}/{round}_{eventIdx}_{playerId}.mp3`
  - Remotion handles audio encoding into the final MP4 automatically
- **Reuse notes**: Audio manifest format unchanged from TTS generation module.

### 4.6 Remotion Entry & Config (`remotion/index.ts`, `remotion/Root.tsx`)

- **Responsibility**: Remotion project registration and composition definition.

  **`index.ts`** (Remotion entry point — `registerRoot`):
  ```typescript
  import { registerRoot } from "remotion";
  import { Root } from "./Root";
  registerRoot(Root);
  ```

  **`Root.tsx`** (Composition registry):
  ```typescript
  export const Root: React.FC = () => (
    <Composition
      id="MasqueradeVideo"
      component={Video}
      width={1920}
      height={1080}
      fps={30}
      durationInFrames={1}  // overridden by calculateMetadata
      defaultProps={{ scriptFile: "" }}
      calculateMetadata={calculateMetadata}
    />
  );
  ```

  **`calculateMetadata`**: Async function that loads the script + audio manifest, calls `buildFrameTimeline()`, and returns `{ durationInFrames, props }`. This makes total duration dynamic per script.

### 4.7 Render Script (`scripts/render-video.mjs`)

- **Responsibility**: Node.js script that bundles the Remotion project and renders to MP4.
- **Public interface**: `node scripts/render-video.mjs <script_filename>`
- **Internal structure**:
  1. Parse CLI args for script filename
  2. Validate script file exists at `output/scripts/{filename}`
  3. Call `bundle()` from `@remotion/bundler` with Remotion entry point + webpack override (Tailwind, path aliases)
  4. Call `renderMedia()` from `@remotion/renderer` with:
     - `composition: "MasqueradeVideo"`
     - `inputProps: { scriptFile: filename }`
     - `codec: "h264"`, `crf: 18`
     - `outputLocation: output/videos/{name}.mp4`
  5. Report progress via `onProgress` callback
  6. Cleanup bundle temp dir
- **Reuse notes**: Wraps Remotion's Node.js API, no custom encoding logic.

### 4.8 Automation Scripts (`scripts/render-video.bat`, `scripts/render-video.sh`)

- **Responsibility**: User-facing one-click wrapper around the Node.js render script.
- **Internal structure**:
  - Validate script argument
  - `cd frontend && node ../scripts/render-video.mjs %SCRIPT%`
  - Print output path on success

### 4.9 Webpack Override for Remotion

- **Responsibility**: Configure Remotion's webpack to support Tailwind CSS and path aliases matching the existing Vite config.
- **Internal structure** (in render script or separate `remotion.config.ts` if needed):
  ```javascript
  // PostCSS + Tailwind
  Config.overrideWebpackConfig((config) => {
    // Add postcss-loader with tailwindcss plugin
    // Add path alias: @ → src/
    return config;
  });
  ```

## 5. Data Model

### 5.1 Core Types (new)

```typescript
// Scene frame range — output of timeline builder
interface SceneFrameRange {
  type: "opening" | "round-title" | "speaking" | "action" | "voting" | "finale";
  startFrame: number;
  durationInFrames: number;
  data: SceneData;  // Union type per scene
}

// Speaking scene data
interface SpeakingData {
  event: GameEvent;
  round: number;
  eventIndex: number;
  tipEndFrame: number;      // relative frame where tip phase ends
  audioFile: string | null; // path relative to public dir
  audioDurationFrames: number;
}

// Action scene data
interface ActionData {
  event: GameEvent;
  round: number;
  eventIndex: number;
  tipEndFrame: number;
}

// Voting scene data
interface VotingData {
  voteResult: VoteResult;
  events: GameEvent[];      // vote events for display
  voterOrder: string[];     // ordered list of voter IDs
}

// Opening scene data
interface OpeningData {
  players: PlayerInfo[];
  gameInfo: GameInfo;
}

// Finale scene data
interface FinaleData {
  result: GameResultData;
  players: PlayerInfo[];
}

// Audio duration map — loaded from manifest + audio file metadata
type AudioDurationMap = Map<string, number>; // key format: "{round}_{eventIndex}_{playerId}"
```

### 5.2 Shared Types (existing, unchanged)

- `GameScript`, `PlayerInfo`, `GameEvent`, `VoteResult`, `GameResultData` from `@/types/game-script.ts`

## 6. API Design

No HTTP APIs. All interaction is via CLI:

| Command | Input | Output |
|:---|:---|:---|
| `node scripts/render-video.mjs <file.json>` | Script JSON filename | `output/videos/<name>.mp4` |
| `scripts/render-video.bat <file.json>` | Script JSON filename | Same as above |
| `scripts/run.bat` | Interactive game selection | Game → TTS → Video pipeline |

## 7. Key Flows

### 7.1 Video Render Flow

See `tech-sequence.puml`.

1. User runs `render-video.mjs game_xxx.json`
2. Script validates input, calls `@remotion/bundler.bundle()` to create webpack bundle
3. Script calls `@remotion/renderer.renderMedia()` with composition ID + props
4. Remotion loads composition, calls `calculateMetadata`:
   a. Fetches `scripts/game_xxx.json` via `staticFile()`
   b. Fetches `audio/{gameId}/manifest.json` via `staticFile()`
   c. Calls `buildFrameTimeline()` → scene list + totalFrames
   d. Returns `{ durationInFrames: totalFrames, props: { script, scenes, audioDurations } }`
5. Remotion renders frame-by-frame:
   - For each frame, `<Video>` determines which `<Sequence>` is active
   - Active scene component renders using `useCurrentFrame()` offset
   - `<Audio>` sequences produce audio samples at correct frames
6. Remotion encodes all frames + audio → H.264 MP4
7. Output written to `output/videos/game_xxx.mp4`

### 7.2 Scene Rendering Flow (per frame)

1. `<Video>` component has N `<Sequence>` blocks (one per scene)
2. Remotion activates the `<Sequence>` whose frame range contains the current frame
3. Scene component calls `useCurrentFrame()` → gets frame offset relative to sequence start
4. Component computes render state:
   - Character count for typewriter: `floor(localFrame * 15 / fps)`
   - Phase determination: `localFrame < tipEndFrame ? "tip" : "content"`
   - Vote reveal index: `floor(localFrame / 36)`
   - Opacity: `interpolate(localFrame, [0, 9], [0, 1], { extrapolateRight: "clamp" })`
5. Component returns JSX with computed values (no setTimeout, no state transitions)

### 7.3 Audio Placement Flow

1. During `calculateMetadata`, for each speaking scene with audio:
   - `audioAbsoluteStartFrame = scene.startFrame + scene.data.tipEndFrame`
2. In `<Video>` render, audio sequences placed at absolute frame positions:
   ```tsx
   <Sequence from={audioAbsoluteStartFrame}>
     <Audio src={staticFile(`audio/${gameId}/${audioFile}`)} />
   </Sequence>
   ```
3. Remotion automatically mixes all audio sequences into final MP4

## 8. Shared Modules & Reuse Strategy

| Module | Used By | Sharing Method |
|:---|:---|:---|
| `@/types/game-script.ts` | Theater + Remotion | Direct import via `@/` alias |
| `ExpressionIcon` | Theater + Remotion | Direct import from `@/components/shared/` |
| Color hash logic | Theater (PlayerAvatar) + Remotion (PlayerAvatarStatic) | Extract to `@/utils/colors.ts`: `getPlayerColor(id)`, `AVATAR_COLORS` |
| Tailwind theme | Theater + Remotion | Same `tailwind.config.ts`, Remotion loads via webpack override |
| Scene duration constants | Timeline builder | `TEXT_SPEED = 15`, `TRANSITION_MS = 500`, etc. in `remotion/timeline.ts` |

**Extraction required**: The current `PlayerAvatar.tsx` uses `framer-motion`. Extract the pure rendering logic (color selection, initial letter, role badge, eliminated styling) into a shared utility or a `PlayerAvatarStatic` component that Remotion scenes import.

## 9. Risks & Notes

| Risk | Mitigation |
|:---|:---|
| **Remotion webpack + Tailwind config** — Remotion uses webpack, not Vite. Tailwind CSS must be configured separately for the Remotion bundle. | Provide webpack override in render script with postcss-loader + tailwindcss. Test Tailwind classes render correctly in Remotion output early. |
| **Audio file access during render** — Remotion's `staticFile()` serves from a `public/` dir. Audio files are in `output/audio/`, scripts in `output/scripts/`. | Configure Remotion's `publicDir` to point to project root `output/` in the `bundle()` call. All `staticFile()` paths relative to that. |
| **Chinese font rendering in headless Chrome** — Remotion uses headless Chromium. Missing Chinese fonts → tofu characters. | Windows: system fonts (Microsoft YaHei) available by default. CI/Linux: install `fonts-noto-cjk`. Add font-family CSS fallback chain. |
| **Large composition render time** — A 60-round werewolf game could produce 30+ minutes of video (~54000 frames at 30fps). | Remotion renders in parallel by default (multiple browser tabs). Monitor memory. Add `--concurrency` flag to render script for tuning. |
| **Audio duration detection** — `calculateMetadata` needs actual MP3 durations. Remotion's `getAudioDurationInSeconds()` requires the audio to be accessible at bundle time. | Use `@remotion/media-utils` `getAudioDurationInSeconds()` in `calculateMetadata`, or pre-compute durations in a sidecar JSON during TTS generation. |
| **Path aliases in webpack** — `@/` alias must work in Remotion's webpack bundle identically to Vite's config. | Add `resolve.alias` in webpack override: `{ "@": path.resolve("src") }`. |

## 10. Change Log

| Version | Date | Changes | Affected Scope | Reason |
|:---|:---|:---|:---|:---|
| v1 | 2026-03-16 | Initial version | ALL | - |
