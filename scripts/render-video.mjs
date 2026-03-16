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

// --- Detect GPU encoder ---

function detectGpuEncoder() {
  // Probe ffmpeg for available hardware encoders: NVENC (NVIDIA), AMF (AMD), QSV (Intel)
  const candidates = ["h264_nvenc", "h264_amf", "h264_qsv"];
  let encoders;
  try {
    encoders = execSync("ffmpeg -encoders -hide_banner", {
      encoding: "utf-8", timeout: 5000, stdio: ["pipe", "pipe", "pipe"],
    });
  } catch (e) {
    // ffmpeg writes to stderr sometimes, check stdout from error
    encoders = e.stdout || "";
  }
  for (const enc of candidates) {
    if (encoders.includes(enc)) {
      // Verify it actually works (driver might be missing)
      try {
        execSync(`ffmpeg -f lavfi -i color=black:s=256x256:d=0.1:r=30 -c:v ${enc} -f null -`, {
          timeout: 10000, stdio: ["pipe", "pipe", "pipe"],
        });
        return enc;
      } catch {
        // Encoder listed but not functional, try next
      }
    }
  }
  return null;
}

const gpuEncoder = detectGpuEncoder();
if (gpuEncoder) {
  console.log(`GPU encoder: ${gpuEncoder}`);
} else {
  console.log("GPU encoder: none (using CPU libx264)");
}
console.log("");

// --- Render ---

console.log("Rendering video...");
const renderStart = Date.now();
let lastProgress = 0;

await renderMedia({
  composition,
  serveUrl: bundleLocation,
  codec: "h264",
  outputLocation: outputFile,
  inputProps: { scriptFile },
  crf: 16,
  chromiumOptions,
  // GPU-accelerated encoding if available, otherwise fall back to CPU
  ffmpegOverride: ({ args }) => {
    if (gpuEncoder) {
      const idx = args.indexOf("libx264");
      if (idx !== -1) {
        args[idx] = gpuEncoder;
        if (gpuEncoder === "h264_nvenc") {
          // NVENC uses -cq instead of -crf
          const crfIdx = args.indexOf("-crf");
          if (crfIdx !== -1) args[crfIdx] = "-cq";
          args.push("-preset", "p4", "-tune", "hq");
        } else if (gpuEncoder === "h264_amf") {
          // AMD AMF uses -quality instead of -crf
          const crfIdx = args.indexOf("-crf");
          if (crfIdx !== -1) { args.splice(crfIdx, 2); }
          args.push("-quality", "quality", "-rc", "cqp", "-qp_i", "16", "-qp_p", "16");
        } else if (gpuEncoder === "h264_qsv") {
          // Intel QSV uses -global_quality
          const crfIdx = args.indexOf("-crf");
          if (crfIdx !== -1) { args[crfIdx] = "-global_quality"; }
        }
      }
    }
    return args;
  },
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
const fileSize = (fs.statSync(outputFile).size / 1024 / 1024).toFixed(1);

console.log("");
console.log("========================================");
console.log(`  Done! ${renderTime}s`);
console.log(`  ${outputFile}`);
console.log(`  ${fileSize} MB`);
console.log("========================================");
