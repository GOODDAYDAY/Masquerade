/**
 * Remotion video render script.
 * Bundles the Remotion project and renders a GameScript to MP4.
 *
 * Usage: node scripts/render-video.mjs <script_filename.json>
 *
 * Prerequisites:
 *   cd frontend && npm install
 *   (remotion + @remotion/bundler + @remotion/renderer + @remotion/media-utils must be installed)
 */

import path from "path";
import fs from "fs";
import { execSync } from "child_process";
import { fileURLToPath } from "url";
import { createRequire } from "module";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const PROJECT_ROOT = path.resolve(__dirname, "..");
const FRONTEND_DIR = path.resolve(PROJECT_ROOT, "frontend");

// Resolve packages from frontend/node_modules (where Remotion is installed)
const require = createRequire(path.resolve(FRONTEND_DIR, "package.json"));
const { bundle } = require("@remotion/bundler");
const { renderMedia, selectComposition } = require("@remotion/renderer");
const { enableTailwind } = require("@remotion/tailwind");
const OUTPUT_DIR = path.resolve(PROJECT_ROOT, "output");
const VIDEOS_DIR = path.resolve(OUTPUT_DIR, "videos");

// --- Parse CLI args ---

const scriptFile = process.argv[2];
if (!scriptFile) {
  console.error("Usage: node scripts/render-video.mjs <script_filename.json>");
  console.error("\nAvailable scripts:");
  const scriptsDir = path.resolve(OUTPUT_DIR, "scripts");
  if (fs.existsSync(scriptsDir)) {
    const files = fs.readdirSync(scriptsDir).filter((f) => f.startsWith("game_") && f.endsWith(".json"));
    files.slice(-10).forEach((f) => console.error(`  ${f}`));
  }
  process.exit(1);
}

const scriptPath = path.resolve(OUTPUT_DIR, "scripts", scriptFile);
if (!fs.existsSync(scriptPath)) {
  console.error(`Script not found: ${scriptPath}`);
  process.exit(1);
}

// --- Ensure output directory ---

fs.mkdirSync(VIDEOS_DIR, { recursive: true });

const outputFile = path.resolve(VIDEOS_DIR, scriptFile.replace(".json", ".mp4"));
const entryPoint = path.resolve(FRONTEND_DIR, "src/remotion/index.ts");

console.log("========================================");
console.log("  Masquerade Video Renderer (Remotion)");
console.log("========================================");
console.log(`Script:  ${scriptFile}`);
console.log(`Output:  ${outputFile}`);
console.log("");

// --- Bundle ---

console.log("Bundling Remotion project...");
const bundleStart = Date.now();

const bundleLocation = await bundle({
  entryPoint,
  webpackOverride: (config) => {
    // Enable Tailwind CSS
    config = enableTailwind(config);

    // Add path alias: @ -> src/
    config.resolve = config.resolve || {};
    config.resolve.alias = {
      ...(config.resolve.alias || {}),
      "@": path.resolve(FRONTEND_DIR, "src"),
    };

    return config;
  },
  // Serve output/ directory as static files for Remotion's staticFile()
  publicDir: OUTPUT_DIR,
});

console.log(`Bundle complete (${((Date.now() - bundleStart) / 1000).toFixed(1)}s)`);

// --- Select composition ---

// Use GPU-accelerated page rendering (ANGLE = Direct3D/OpenGL backend)
const chromiumOptions = { gl: "angle" };

console.log("Loading composition...");
const composition = await selectComposition({
  serveUrl: bundleLocation,
  id: "MasqueradeVideo",
  inputProps: { scriptFile },
  chromiumOptions,
});

console.log(`Composition: ${composition.durationInFrames} frames @ ${composition.fps}fps = ${(composition.durationInFrames / composition.fps).toFixed(1)}s`);
console.log(`Resolution:  ${composition.width}x${composition.height}`);
console.log("");

// --- Detect system ffmpeg with GPU encoder ---
// Remotion's built-in ffmpeg has no hardware encoders.
// Strategy: use Remotion's built-in ffmpeg for rendering (it handles piping, audio mixing, etc.),
// then re-encode the output with system ffmpeg + NVENC as a fast post-process step.

function detectGpuEncoding() {
  let ffmpegPath;
  try {
    ffmpegPath = execSync("where ffmpeg", {
      encoding: "utf-8", timeout: 5000, stdio: ["pipe", "pipe", "pipe"],
    }).trim().split("\n")[0].trim();
  } catch {
    return null;
  }
  if (!ffmpegPath || !fs.existsSync(ffmpegPath)) return null;

  const candidates = ["h264_nvenc", "h264_amf", "h264_qsv"];
  let encoders;
  try {
    encoders = execSync(`"${ffmpegPath}" -encoders -hide_banner`, {
      encoding: "utf-8", timeout: 5000, stdio: ["pipe", "pipe", "pipe"],
    });
  } catch (e) {
    encoders = e.stdout || "";
  }

  for (const enc of candidates) {
    if (encoders.includes(enc)) {
      try {
        execSync(`"${ffmpegPath}" -f lavfi -i color=black:s=256x256:d=0.1:r=30 -c:v ${enc} -f null -`, {
          timeout: 10000, stdio: ["pipe", "pipe", "pipe"],
        });
        return { ffmpegPath, encoder: enc };
      } catch { /* not functional */ }
    }
  }
  return null;
}

const gpu = detectGpuEncoding();
if (gpu) {
  console.log(`GPU encoder: ${gpu.encoder} (post-process re-encode)`);
} else {
  console.log("GPU encoder: none (CPU only)");
}
console.log("");

// --- Render ---

console.log("Rendering video...");
const renderStart = Date.now();
let lastProgress = 0;

// If GPU available, render to temp file first, then re-encode with NVENC
const renderTarget = gpu ? outputFile.replace(".mp4", "_cpu.mp4") : outputFile;

await renderMedia({
  composition,
  serveUrl: bundleLocation,
  codec: "h264",
  outputLocation: renderTarget,
  inputProps: { scriptFile },
  crf: 16,
  chromiumOptions,
  onProgress: ({ progress }) => {
    const pct = Math.round(progress * 100);
    if (pct >= lastProgress + 5) {
      lastProgress = pct;
      const elapsed = ((Date.now() - renderStart) / 1000).toFixed(0);
      console.log(`  ${pct}% (${elapsed}s)`);
    }
  },
});

const renderTime = ((Date.now() - renderStart) / 1000).toFixed(1);

// GPU post-process: re-encode video track with NVENC, copy audio
if (gpu) {
  console.log("");
  console.log(`Re-encoding with ${gpu.encoder}...`);
  const reencodeStart = Date.now();
  try {
    const nvencArgs = gpu.encoder === "h264_nvenc"
      ? "-c:v h264_nvenc -preset p4 -tune hq -cq 16"
      : gpu.encoder === "h264_amf"
      ? "-c:v h264_amf -quality quality -rc cqp -qp_i 16 -qp_p 16"
      : `-c:v ${gpu.encoder} -global_quality 16`;

    execSync(
      `"${gpu.ffmpegPath}" -y -i "${renderTarget}" ${nvencArgs} -c:a copy "${outputFile}"`,
      { stdio: ["pipe", "pipe", "pipe"], timeout: 600000 },
    );
    const reencodeTime = ((Date.now() - reencodeStart) / 1000).toFixed(1);
    console.log(`Re-encode complete (${reencodeTime}s)`);
    // Clean up temp file
    fs.unlinkSync(renderTarget);
  } catch (e) {
    console.warn(`GPU re-encode failed, keeping CPU output: ${e.message}`);
    // Fall back to CPU output
    if (fs.existsSync(renderTarget)) {
      fs.renameSync(renderTarget, outputFile);
    }
  }
}

const fileSize = (fs.statSync(outputFile).size / 1024 / 1024).toFixed(1);

console.log("");
console.log("========================================");
console.log(`  Done! ${renderTime}s render` + (gpu ? ` + GPU re-encode` : ""));
console.log(`  ${outputFile}`);
console.log(`  ${fileSize} MB`);
console.log("========================================");
