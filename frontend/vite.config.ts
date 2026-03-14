import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";
import { createReadStream, existsSync, statSync } from "fs";

// Serve project root's output/ directory at /output/
function serveOutputPlugin() {
  const outputRoot = resolve(__dirname, "..", "output");
  return {
    name: "serve-output",
    configureServer(server: { middlewares: { use: Function } }) {
      server.middlewares.use((req: any, res: any, next: Function) => {
        if (!req.url?.startsWith("/output/")) return next();
        const filePath = resolve(outputRoot, decodeURIComponent(req.url.replace("/output/", "")));
        // Prevent path traversal
        if (!filePath.startsWith(outputRoot)) return next();
        if (!existsSync(filePath) || !statSync(filePath).isFile()) return next();

        const ext = filePath.split(".").pop();
        const mimeMap: Record<string, string> = {
          json: "application/json",
          mp3: "audio/mpeg",
        };
        res.setHeader("Content-Type", mimeMap[ext ?? ""] ?? "application/octet-stream");
        createReadStream(filePath).pipe(res);
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), serveOutputPlugin()],
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
});
