/**
 * Remotion video render script.
 * Bundles the Remotion project and renders a GameScript to MP4.
 *
 * Features:
 *   - Auto-detects system GPUs and selects the optimal one for rendering
 *   - Monkey-patches Remotion's browser launcher to prefer discrete GPU
 *   - Uses GPU hardware encoder (NVENC/AMF/QSV) for post-process re-encoding
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

// =====================================================================
// GPU Auto-Detection & Selection (REQ-016)
// Detects all system GPUs, selects the optimal one, and patches
// Remotion's browser launcher to prefer the discrete GPU.
// =====================================================================

// --- GPU Detection ---

/** Known integrated GPU name patterns (case-insensitive substring match) */
const INTEGRATED_GPU_PATTERNS = [
  "radeon(tm) graphics",  // AMD APU (no model suffix like RX xxxx)
  "uhd graphics",         // Intel UHD
  "iris",                 // Intel Iris
  "vega",                 // AMD Vega (in APU)
];

/**
 * Detect all GPUs via PowerShell Win32_VideoController.
 * Fallback to nvidia-smi if PowerShell fails.
 * Returns array of { name, vendor, type, vendorId }.
 */
function detectSystemGpus() {
  // Strategy 1: PowerShell (covers all vendors)
  try {
    const psCmd = `powershell -NoProfile -Command "Get-CimInstance Win32_VideoController | Select-Object Name,PNPDeviceID,AdapterRAM | ConvertTo-Json -Compress"`;
    const output = execSync(psCmd, { encoding: "utf-8", timeout: 5000, stdio: ["pipe", "pipe", "pipe"] });
    const raw = JSON.parse(output);
    const controllers = Array.isArray(raw) ? raw : [raw];

    return controllers
      .filter((c) => c.Name && c.PNPDeviceID)
      .map((c) => {
        const venMatch = c.PNPDeviceID.match(/VEN_([0-9A-Fa-f]{4})/);
        const vendorId = venMatch ? `0x${venMatch[1].toUpperCase()}` : null;
        const vendor = vendorId === "0x10DE" ? "nvidia"
          : vendorId === "0x1002" ? "amd"
          : vendorId === "0x8086" ? "intel"
          : "unknown";
        const nameLower = c.Name.toLowerCase();
        const ramGB = c.AdapterRAM ? c.AdapterRAM / (1024 * 1024 * 1024) : 0;
        // Classify as integrated if name matches known iGPU patterns AND VRAM is small
        const isIntegrated = INTEGRATED_GPU_PATTERNS.some((p) => nameLower.includes(p)) || ramGB <= 2;
        return {
          name: c.Name,
          vendor,
          type: isIntegrated ? "integrated" : "discrete",
          vendorId,
        };
      });
  } catch { /* PowerShell failed, try fallback */ }

  // Strategy 2: nvidia-smi (NVIDIA only)
  try {
    const output = execSync("nvidia-smi --query-gpu=name --format=csv,noheader,nounits", {
      encoding: "utf-8", timeout: 5000, stdio: ["pipe", "pipe", "pipe"],
    });
    return output.trim().split("\n").filter(Boolean).map((name) => ({
      name: name.trim(),
      vendor: "nvidia",
      type: "discrete",
      vendorId: "0x10DE",
    }));
  } catch { /* nvidia-smi not available */ }

  return [];
}

/**
 * Select the optimal GPU from the detected list.
 * Priority: NVIDIA discrete > AMD discrete > Intel discrete > any iGPU > null
 */
function selectOptimalGpu(gpus) {
  const priority = [
    (g) => g.vendor === "nvidia" && g.type === "discrete",
    (g) => g.vendor === "amd" && g.type === "discrete",
    (g) => g.vendor === "intel" && g.type === "discrete",
    (g) => g.type === "integrated",
  ];
  for (const pred of priority) {
    const match = gpus.find(pred);
    if (match) return match;
  }
  return null;
}

// --- Chromium GPU Patch ---

/**
 * Monkey-patch Remotion's launchChrome to inject GPU preference args.
 * This makes Chrome's ANGLE D3D11 backend prefer the discrete GPU.
 */
function patchRemotionBrowser(selectedGpu) {
  if (!selectedGpu || selectedGpu.type !== "discrete") return false;

  try {
    // Bypass Remotion's package.json "exports" field by using absolute filesystem path
    const launcherPath = path.resolve(FRONTEND_DIR, "node_modules/@remotion/renderer/dist/browser/Launcher.js");
    const launcherRequire = createRequire(launcherPath);
    const launcherModule = launcherRequire(launcherPath);
    const originalLaunchChrome = launcherModule.launchChrome;

    if (typeof originalLaunchChrome !== "function") {
      console.warn("  [WARN] Remotion Launcher.launchChrome is not a function, patch skipped");
      return false;
    }

    launcherModule.launchChrome = async (opts) => {
      const extraArgs = [
        "--use-angle=d3d11",   // Force D3D11 backend for ANGLE
        "--enable-gpu",        // Ensure GPU compositing is enabled
      ];
      opts.args = [...(opts.args || []), ...extraArgs];
      return originalLaunchChrome(opts);
    };

    // Set environment variables for DXGI GPU preference (Windows 10 1803+)
    // DXGI_GPU_PREFERENCE=2 tells the D3D runtime to prefer the high-performance GPU
    process.env.DXGI_GPU_PREFERENCE = "2";
    // SHIM_MCCOMPAT hints Windows Hybrid Graphics to select the discrete GPU
    process.env.SHIM_MCCOMPAT = "0x800000001";

    return true;
  } catch (e) {
    console.warn(`  [WARN] Browser GPU patch failed: ${e.message}`);
    return false;
  }
}

// --- Encoder Detection (vendor-aware) ---

/**
 * Detect the best available GPU encoder for ffmpeg post-process re-encoding.
 * Encoder candidates are ordered based on the selected rendering GPU vendor.
 */
function detectGpuEncoding(selectedGpu) {
  let ffmpegPath;
  try {
    ffmpegPath = execSync("where ffmpeg", {
      encoding: "utf-8", timeout: 5000, stdio: ["pipe", "pipe", "pipe"],
    }).trim().split("\n")[0].trim();
  } catch {
    return null;
  }
  if (!ffmpegPath || !fs.existsSync(ffmpegPath)) return null;

  // Order candidates based on selected GPU vendor for optimal affinity
  let candidates;
  if (selectedGpu?.vendor === "amd") {
    candidates = ["h264_amf", "h264_nvenc", "h264_qsv"];
  } else if (selectedGpu?.vendor === "intel") {
    candidates = ["h264_qsv", "h264_nvenc", "h264_amf"];
  } else {
    // Default / NVIDIA: prefer NVENC
    candidates = ["h264_nvenc", "h264_amf", "h264_qsv"];
  }

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
        // Verify the encoder actually works with a tiny test encode
        execSync(`"${ffmpegPath}" -f lavfi -i color=black:s=256x256:d=0.1:r=30 -c:v ${enc} -f null -`, {
          timeout: 10000, stdio: ["pipe", "pipe", "pipe"],
        });
        return { ffmpegPath, encoder: enc };
      } catch { /* encoder listed but not functional */ }
    }
  }
  return null;
}

// --- Run GPU detection pipeline ---

const detectedGpus = detectSystemGpus();
const selectedGpu = selectOptimalGpu(detectedGpus);
const patchApplied = patchRemotionBrowser(selectedGpu);

console.log("========================================");
console.log("  GPU Detection Report");
console.log("========================================");
if (detectedGpus.length === 0) {
  console.log("  GPUs found: none (will use default rendering)");
} else {
  console.log("  GPUs found:");
  detectedGpus.forEach((g, i) => {
    const marker = selectedGpu && g.name === selectedGpu.name && g.vendorId === selectedGpu.vendorId ? " <-- selected" : "";
    console.log(`    [${i + 1}] ${g.name} (${g.type})${marker}`);
  });
}
console.log("");
console.log(`  Page rendering : ${selectedGpu ? `${selectedGpu.name} (via ANGLE D3D11)` : "system default"}`);
console.log(`  Browser patch  : ${patchApplied ? "applied" : "skipped"}`);

// Detect encoder (vendor-aware ordering)
const gpuEncoder = detectGpuEncoding(selectedGpu);
console.log(`  Video encoding : ${gpuEncoder ? `${gpuEncoder.encoder}` : "libx264 (CPU)"}`);
console.log("========================================");
console.log("");

// Use GPU-accelerated page rendering (ANGLE = Direct3D/OpenGL backend)
const chromiumOptions = { gl: "angle" };

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

// --- Render ---

console.log("Rendering video...");
const renderStart = Date.now();
let lastProgress = 0;

// If GPU encoder available, render to temp file first, then re-encode with hardware encoder
const renderTarget = gpuEncoder ? outputFile.replace(".mp4", "_cpu.mp4") : outputFile;

// Use all CPU cores for maximum parallelism
const cpuCount = (await import("os")).default.cpus().length;

await renderMedia({
  composition,
  serveUrl: bundleLocation,
  codec: "h264",
  outputLocation: renderTarget,
  inputProps: { scriptFile },
  crf: 18,
  chromiumOptions,
  concurrency: cpuCount,
  x264Preset: "fast",
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

// GPU post-process: re-encode video track with hardware encoder, copy audio
if (gpuEncoder) {
  console.log("");
  console.log(`Re-encoding with ${gpuEncoder.encoder}...`);
  const reencodeStart = Date.now();
  try {
    const encArgs = gpuEncoder.encoder === "h264_nvenc"
      ? "-c:v h264_nvenc -preset p4 -tune hq -cq 16"
      : gpuEncoder.encoder === "h264_amf"
      ? "-c:v h264_amf -quality quality -rc cqp -qp_i 16 -qp_p 16"
      : `-c:v ${gpuEncoder.encoder} -global_quality 16`;

    execSync(
      `"${gpuEncoder.ffmpegPath}" -y -i "${renderTarget}" ${encArgs} -c:a copy "${outputFile}"`,
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
console.log(`  Done! ${renderTime}s render` + (gpuEncoder ? ` + GPU re-encode` : ""));
console.log(`  ${outputFile}`);
console.log(`  ${fileSize} MB`);
console.log("========================================");
