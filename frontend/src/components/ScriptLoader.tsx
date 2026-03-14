/**
 * F-07: Script loader — drag & drop JSON upload + URL param loading.
 */

import { useState, useCallback, useEffect, useRef } from "react";
import { motion } from "framer-motion";
import type { GameScript } from "@/types/game-script";
import { isValidGameScript } from "@/types/game-script";

interface ScriptLoaderProps {
  onLoad: (script: GameScript, filename: string) => void;
}

export default function ScriptLoader({ onLoad }: ScriptLoaderProps) {
  const [error, setError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Check URL param on mount
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const scriptUrl = params.get("script");
    if (scriptUrl) {
      loadFromUrl(scriptUrl);
    }
  }, []);

  const loadFromUrl = async (url: string) => {
    setError(null);
    try {
      const resp = await fetch(url);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data: unknown = await resp.json();
      const filename = url.split("/").pop() ?? "unknown.json";
      validateAndLoad(data, filename);
    } catch (e) {
      setError(`Failed to load script from URL: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const validateAndLoad = useCallback(
    (data: unknown, filename: string) => {
      if (!isValidGameScript(data)) {
        setError("Invalid GameScript format: missing game, players, or rounds fields");
        return;
      }
      setError(null);
      onLoad(data, filename);
    },
    [onLoad],
  );

  const handleFile = useCallback(
    (file: File) => {
      if (!file.name.endsWith(".json")) {
        setError("Please upload a JSON file");
        return;
      }
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const data: unknown = JSON.parse(reader.result as string);
          validateAndLoad(data, file.name);
        } catch {
          setError("Invalid JSON file");
        }
      };
      reader.readAsText(file);
    },
    [validateAndLoad],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragging(false);
  }, []);

  return (
    <div className="flex flex-col items-center justify-center min-h-screen px-8">
      <motion.h1
        className="text-4xl font-bold text-white mb-2"
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        Masquerade Theater
      </motion.h1>
      <motion.p
        className="text-gray-400 mb-12"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.2 }}
      >
        选择一个游戏剧本开始回放
      </motion.p>

      {/* Drop zone */}
      <motion.div
        className={`w-full max-w-lg border-2 border-dashed rounded-2xl p-12 text-center cursor-pointer transition-colors ${
          isDragging
            ? "border-theater-accent bg-theater-accent/10"
            : "border-theater-border hover:border-gray-500"
        }`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => fileInputRef.current?.click()}
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.3 }}
        whileHover={{ scale: 1.02 }}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".json"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
          }}
        />
        <div className="text-5xl mb-4">📂</div>
        <p className="text-lg text-gray-300">
          拖拽 JSON 剧本到这里
        </p>
        <p className="text-sm text-gray-500 mt-2">
          或点击选择文件
        </p>
      </motion.div>

      {/* Error message */}
      {error && (
        <motion.p
          className="mt-6 text-theater-danger text-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
        >
          {error}
        </motion.p>
      )}

      <p className="mt-8 text-xs text-gray-600">
        支持 URL 参数加载：?script=path/to/game.json
      </p>
    </div>
  );
}
