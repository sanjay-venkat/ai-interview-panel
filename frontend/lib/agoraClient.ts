import type { IAgoraRTCClient, IMicrophoneAudioTrack, IRemoteAudioTrack } from "agora-rtc-sdk-ng";

export type RemoteAgentTrack = { uid: string | number; track: IRemoteAudioTrack };

export class InterviewRoom {
  client: IAgoraRTCClient | null = null;
  micTrack: IMicrophoneAudioTrack | null = null;
  onRemoteTrack?: (info: RemoteAgentTrack) => void;
  onRemoteLeft?: (uid: string | number) => void;

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

    await client.join(appId, channel, token || null, uid);
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
