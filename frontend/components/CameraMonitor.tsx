"use client";

import { useEffect, useRef, useState } from "react";
import { FaceProctor, ProctorEventType, ProctorStatus } from "@/lib/faceProctor";

interface Props {
  stream: MediaStream | null;
  onEvent: (type: ProctorEventType) => void;
  tiltCount: number;
  awayCount: number;
}

const STATUS_LABEL: Record<ProctorStatus, string> = {
  starting: "Starting monitor…",
  ok: "Monitoring",
  tilt: "Head tilt detected",
  away: "Face not visible",
  unavailable: "Monitor unavailable",
};

export default function CameraMonitor({ stream, onEvent, tiltCount, awayCount }: Props) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [status, setStatus] = useState<ProctorStatus>("starting");

  useEffect(() => {
    if (!stream || !videoRef.current || !canvasRef.current) return;
    const video = videoRef.current;
    video.srcObject = stream;
    video.play().catch(() => {});

    const proctor = new FaceProctor(video, canvasRef.current, onEvent, setStatus);
    proctor.start();
    return () => proctor.stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stream]);

  return (
    <div className={`camera-monitor status-${status}`}>
      <video ref={videoRef} muted playsInline className="camera-monitor-video" />
      <canvas ref={canvasRef} style={{ display: "none" }} />
      <div className="camera-monitor-badge">
        <span className="camera-monitor-dot" />
        {STATUS_LABEL[status]}
      </div>
      {status !== "unavailable" && (
        <div className="camera-monitor-counts">
          {tiltCount} tilt &middot; {awayCount} away
        </div>
      )}
    </div>
  );
}
