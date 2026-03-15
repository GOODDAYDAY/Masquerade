/**
 * Audio manager — preloads all MP3 files on init, exposes duration.
 * Stores audio as blob URLs for reliable playback.
 */

interface AudioFileEntry {
  file: string;
  round: number;
  event_index: number;
  player_id: string;
}

interface AudioManifest {
  game_id: string;
  files: AudioFileEntry[];
}

interface PreloadedAudio {
  blobUrl: string;
  duration: number; // seconds
}

function makeKey(round: number, eventIndex: number, playerId: string): string {
  return `${round}_${eventIndex}_${playerId}`;
}

export class AudioManager {
  private audioMap = new Map<string, PreloadedAudio>();
  private currentAudio: HTMLAudioElement | null = null;

  /** Load manifest and preload ALL audio files as blob URLs. */
  async loadAndPreload(audioDir: string): Promise<void> {
    let manifest: AudioManifest;
    try {
      const resp = await fetch(`${audioDir}/manifest.json`);
      if (!resp.ok) return;
      manifest = (await resp.json()) as AudioManifest;
    } catch {
      return;
    }

    console.log("Preloading %d audio files...", manifest.files.length);

    const promises = manifest.files.map(async (entry) => {
      const url = `${audioDir}/${encodeURIComponent(entry.file)}`;
      try {
        // Fetch as blob for reliable playback
        const resp = await fetch(url);
        if (!resp.ok) return;
        const blob = await resp.blob();
        const blobUrl = URL.createObjectURL(blob);

        // Get duration
        const duration = await new Promise<number>((resolve) => {
          const audio = new Audio(blobUrl);
          audio.onloadedmetadata = () => resolve(audio.duration);
          audio.onerror = () => resolve(0);
        });

        const key = makeKey(entry.round, entry.event_index, entry.player_id);
        this.audioMap.set(key, { blobUrl, duration });
      } catch {
        console.warn("Failed to preload: %s", entry.file);
      }
    });

    await Promise.all(promises);
    console.log("Audio preloaded: %d files ready", this.audioMap.size);
  }

  /** Get audio duration in milliseconds. Returns 0 if not available. */
  getDurationMs(round: number, eventIndex: number, playerId: string): number {
    const item = this.audioMap.get(makeKey(round, eventIndex, playerId));
    return item ? item.duration * 1000 : 0;
  }

  /** Play audio for a speaking event. */
  play(round: number, eventIndex: number, playerId: string): void {
    this.stop();
    const key = makeKey(round, eventIndex, playerId);
    const item = this.audioMap.get(key);
    if (!item) {
      console.warn("No audio for: %s", key);
      return;
    }

    const audio = new Audio(item.blobUrl);
    this.currentAudio = audio;
    audio.play().catch((e) => {
      console.warn("Play failed for %s: %s", key, e);
    });
  }

  /** Pause current audio (resumable) */
  pause(): void {
    if (this.currentAudio) {
      this.currentAudio.pause();
    }
  }

  /** Resume paused audio */
  resume(): void {
    if (this.currentAudio && this.currentAudio.paused) {
      this.currentAudio.play().catch(() => {});
    }
  }

  /** Stop and discard current audio */
  stop(): void {
    if (this.currentAudio) {
      this.currentAudio.pause();
      this.currentAudio.currentTime = 0;
      this.currentAudio = null;
    }
  }

  get ready(): boolean {
    return this.audioMap.size > 0;
  }

  destroy(): void {
    this.stop();
    // Release blob URLs
    for (const item of this.audioMap.values()) {
      URL.revokeObjectURL(item.blobUrl);
    }
    this.audioMap.clear();
  }
}
