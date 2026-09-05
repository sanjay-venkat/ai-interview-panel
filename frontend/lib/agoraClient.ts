import type { IAgoraRTCClient, IMicrophoneAudioTrack, IRemoteAudioTrack } from "agora-rtc-sdk-ng";

export type RemoteAgentTrack = { uid: string | number; track: IRemoteAudioTrack };
export type VolumeLevel = { uid: string | number; level: number };

export class InterviewRoom {
  client: IAgoraRTCClient | null = null;
  micTrack: IMicrophoneAudioTrack | null = null;
  onRemoteTrack?: (info: RemoteAgentTrack) => void;
  onRemoteLeft?: (uid: string | number) => void;
  // Fires ~every 200ms with each active uid's real audio energy (0-100) on
  // the RTC channel. This is what actually drives "who is speaking" in the
  // UI -- text-generation timing (when the LLM finishes streaming a
  // response) is a poor proxy for it, since Agora's TTS can still be
  // playing that response's audio for several more seconds after the text
  // stream itself has already ended.
  onVolumeIndicator?: (levels: VolumeLevel[]) => void;

  async join(appId: string, channel: string, token: string, uid: number) {
    // agora-rtc-sdk-ng touches `window` at import time, which breaks Next.js's
    // build-time prerender (runs on the server, no window). Loading it
    // dynamically here means it's only ever pulled in inside the browser.
    const AgoraRTC = (await import("agora-rtc-sdk-ng")).default;
    const client = AgoraRTC.createClient({ mode: "rtc", codec: "vp8" });
    this.client = client;

    client.on("user-published", async (user, mediaType) => {
      if (mediaType !== "audio") return;
      await client.subscribe(user, mediaType);
      const track = user.audioTrack;
      if (track) {
        track.play();
        this.onRemoteTrack?.({ uid: user.uid, track });
      }
    });
    client.on("user-left", (user) => {
      this.onRemoteLeft?.(user.uid);
    });
    client.on("volume-indicator", (volumes) => {
      this.onVolumeIndicator?.(volumes.map((v) => ({ uid: v.uid, level: v.level })));
    });

    await client.join(appId, channel, token || null, uid);
    client.enableAudioVolumeIndicator();
    this.micTrack = await AgoraRTC.createMicrophoneAudioTrack();
    await client.publish([this.micTrack]);
  }

  async leave() {
    this.micTrack?.stop();
    this.micTrack?.close();
    await this.client?.leave();
    this.client = null;
  }

  setMuted(muted: boolean) {
    this.micTrack?.setEnabled(!muted);
  }
}
