/**
 * Audio manager — preloads all MP3 files on init, exposes duration.
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
  audio: HTMLAudioElement;
  duration: number; // seconds
  entry: AudioFileEntry;
}

function makeKey(round: number, eventIndex: number, playerId: string): string {
  return `${round}_${eventIndex}_${playerId}`;
}

export class AudioManager {
  private audioMap = new Map<string, PreloadedAudio>();
  private currentAudio: HTMLAudioElement | null = null;

  /** Load manifest and preload ALL audio files. Resolves when all durations are known. */
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

    const promises = manifest.files.map((entry) => {
      return new Promise<void>((resolve) => {
        const url = `${audioDir}/${encodeURIComponent(entry.file)}`;
        const audio = new Audio();
        audio.preload = "auto";
        audio.src = url;

        audio.onloadedmetadata = () => {
          this.audioMap.set(makeKey(entry.round, entry.event_index, entry.player_id), {
            audio, duration: audio.duration, entry,
          });
          resolve();
        };
        audio.onerror = () => {
          console.warn("Failed to preload: %s", entry.file);
          resolve();
        };
      });
    });

    await Promise.all(promises);
    console.log("Audio preloaded: %d files ready", this.audioMap.size);
  }

  /** Get audio duration in milliseconds. Returns 0 if not available. */
  getDurationMs(round: number, eventIndex: number, playerId: string): number {
    const item = this.audioMap.get(makeKey(round, eventIndex, playerId));
    return item ? item.duration * 1000 : 0;
  }

  /** Play audio for a speaking event. Fire and forget. */
  play(round: number, eventIndex: number, playerId: string): void {
    this.stop();
    const item = this.audioMap.get(makeKey(round, eventIndex, playerId));
    if (!item) return;

    // Clone so we can replay the same audio multiple times
    const audio = item.audio.cloneNode(true) as HTMLAudioElement;
    this.currentAudio = audio;
    audio.currentTime = 0;
    audio.play().catch(() => {
      console.warn("Failed to play: %s", item.entry.file);
    });
  }

  stop(): void {
    if (this.currentAudio) {
      this.currentAudio.pause();
      this.currentAudio = null;
    }
  }

  get ready(): boolean {
    return this.audioMap.size > 0;
  }

  destroy(): void {
    this.stop();
    this.audioMap.clear();
  }
}
