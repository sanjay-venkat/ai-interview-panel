// Lightweight browser-side proctoring: loads OpenCV.js (WebAssembly build of
// real OpenCV, not a mock) and runs Haar-cascade face + eye detection against
// the candidate's own camera feed, entirely client-side — no video frame
// ever leaves the browser. Two signals are tracked, matching what
// commercial AI-interview proctoring tools flag:
//   - "away"  — no frontal face detected for a sustained stretch (looked
//               away, left the frame, or turned far enough that the
//               frontal-face cascade no longer matches).
//   - "tilt"  — a face IS detected, but the eye-line is rotated past a
//               threshold (head tilted sideways).
// Both are debounced (state only flips, and an event only fires, after a
// short sustained streak) so a single noisy frame doesn't count as an
// incident, and a *sustained* tilt/away only counts once until the
// candidate returns to normal.

export type ProctorEventType = "tilt" | "away";
export type ProctorStatus = "starting" | "ok" | "tilt" | "away" | "unavailable";

const OPENCV_SRC = "https://docs.opencv.org/4.9.0/opencv.js";
const FACE_CASCADE_URL =
  "https://raw.githubusercontent.com/opencv/opencv/4.x/data/haarcascades/haarcascade_frontalface_default.xml";
const EYE_CASCADE_URL =
  "https://raw.githubusercontent.com/opencv/opencv/4.x/data/haarcascades/haarcascade_eye.xml";

const CHECK_INTERVAL_MS = 500;
const AWAY_STREAK_TO_FLAG = 2; // ~1s of no detected face before counting an incident
const TILT_STREAK_TO_FLAG = 2; // ~1s of sustained tilt before counting an incident
const TILT_THRESHOLD_DEGREES = 18;

let openCvLoadPromise: Promise<void> | null = null;

function loadOpenCv(): Promise<void> {
  if (typeof window === "undefined") return Promise.reject(new Error("no window"));
  const w = window as unknown as { cv?: OpenCv };
  if (w.cv && (w.cv as unknown as { Mat?: unknown }).Mat) return Promise.resolve();
  if (openCvLoadPromise) return openCvLoadPromise;

  openCvLoadPromise = new Promise((resolve, reject) => {
    const onReady = () => {
      const cv = (window as unknown as { cv: OpenCv }).cv;
      if ((cv as unknown as { Mat?: unknown }).Mat) resolve();
      else (cv as unknown as { onRuntimeInitialized: () => void }).onRuntimeInitialized = () => resolve();
    };
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${OPENCV_SRC}"]`);
    if (existing) {
      if ((window as unknown as { cv?: OpenCv }).cv) onReady();
      else existing.addEventListener("load", onReady);
      return;
    }
    const script = document.createElement("script");
    script.src = OPENCV_SRC;
    script.async = true;
    script.onload = onReady;
    script.onerror = () => reject(new Error("Failed to load OpenCV.js"));
    document.body.appendChild(script);
  });
  return openCvLoadPromise;
}

// Minimal shape of the parts of the OpenCV.js API this file actually uses —
// the real global has hundreds of members with no official TS types.
interface OpenCv {
  Mat: new () => CvMat;
  RectVector: new () => CvRectVector;
  Size: new (w: number, h: number) => unknown;
  CascadeClassifier: new () => CvCascadeClassifier;
  COLOR_RGBA2GRAY: number;
  imread: (canvas: HTMLCanvasElement) => CvMat;
  cvtColor: (src: CvMat, dst: CvMat, code: number) => void;
  FS: { analyzePath: (path: string) => { exists: boolean } };
  FS_createDataFile: (
    parent: string,
    name: string,
    data: Uint8Array,
    canRead: boolean,
    canWrite: boolean,
    canOwn: boolean
  ) => void;
}
interface CvRect {
  x: number;
  y: number;
  width: number;
  height: number;
}
interface CvRectVector {
  size: () => number;
  get: (i: number) => CvRect;
  delete: () => void;
}
interface CvMat {
  delete: () => void;
  roi: (rect: CvRect) => CvMat;
}
interface CvCascadeClassifier {
  load: (path: string) => void;
  detectMultiScale: (
    image: CvMat,
    objects: CvRectVector,
    scaleFactor: number,
    minNeighbors: number,
    flags: number,
    minSize: unknown
  ) => void;
  delete: () => void;
}

async function fetchToFS(cv: OpenCv, url: string, filename: string) {
  if (cv.FS.analyzePath("/" + filename).exists) return;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`failed to fetch ${filename}: ${res.status}`);
  const buf = new Uint8Array(await res.arrayBuffer());
  cv.FS_createDataFile("/", filename, buf, true, false, false);
}

export class FaceProctor {
  private video: HTMLVideoElement;
  private canvas: HTMLCanvasElement;
  private onEvent: (type: ProctorEventType) => void;
  private onStatus?: (status: ProctorStatus) => void;
  private faceCascade: CvCascadeClassifier | null = null;
  private eyeCascade: CvCascadeClassifier | null = null;
  private timer: number | null = null;
  private stopped = false;
  private awayStreak = 0;
  private tiltStreak = 0;
  private inAway = false;
  private inTilt = false;

  constructor(
    video: HTMLVideoElement,
    canvas: HTMLCanvasElement,
    onEvent: (type: ProctorEventType) => void,
    onStatus?: (status: ProctorStatus) => void
  ) {
    this.video = video;
    this.canvas = canvas;
    this.onEvent = onEvent;
    this.onStatus = onStatus;
  }

  async start() {
    this.onStatus?.("starting");
    try {
      await loadOpenCv();
      const cv = (window as unknown as { cv: OpenCv }).cv;
      await fetchToFS(cv, FACE_CASCADE_URL, "face.xml");
      await fetchToFS(cv, EYE_CASCADE_URL, "eye.xml");
      this.faceCascade = new cv.CascadeClassifier();
      this.faceCascade.load("face.xml");
      this.eyeCascade = new cv.CascadeClassifier();
      this.eyeCascade.load("eye.xml");
    } catch {
      // Camera monitoring is a value-add, not a hard requirement — if the
      // OpenCV.js CDN is unreachable, degrade quietly rather than blocking
      // the interview itself.
      this.onStatus?.("unavailable");
      return;
    }
    if (this.stopped) return;
    this.loop();
  }

  private loop = () => {
    if (this.stopped) return;
    try {
      this.tick();
    } catch {
      // A single bad frame shouldn't kill the loop.
    }
    this.timer = window.setTimeout(this.loop, CHECK_INTERVAL_MS);
  };

  private tick() {
    const cv = (window as unknown as { cv?: OpenCv }).cv;
    if (!cv || !this.faceCascade || !this.eyeCascade) return;
    if (this.video.readyState < 2 || this.video.videoWidth === 0) return;

    this.canvas.width = this.video.videoWidth;
    this.canvas.height = this.video.videoHeight;
    const ctx = this.canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(this.video, 0, 0, this.canvas.width, this.canvas.height);

    const src = cv.imread(this.canvas);
    const gray = new cv.Mat();
    cv.cvtColor(src, gray, cv.COLOR_RGBA2GRAY);
    const faces = new cv.RectVector();
    this.faceCascade.detectMultiScale(gray, faces, 1.1, 4, 0, new cv.Size(60, 60));

    if (faces.size() === 0) {
      this.updateStreak("away", true);
      this.updateStreak("tilt", false);
    } else {
      this.updateStreak("away", false);
      const face = faces.get(0);
      const roi = gray.roi(face);
      const eyes = new cv.RectVector();
      this.eyeCascade.detectMultiScale(roi, eyes, 1.1, 5, 0, new cv.Size(15, 15));

      if (eyes.size() >= 2) {
        const centers: { x: number; y: number }[] = [];
        for (let i = 0; i < eyes.size(); i++) {
          const e = eyes.get(i);
          centers.push({ x: e.x + e.width / 2, y: e.y + e.height / 2 });
        }
        centers.sort((a, b) => a.x - b.x);
        const left = centers[0];
        const right = centers[centers.length - 1];
        const angle = (Math.atan2(right.y - left.y, right.x - left.x) * 180) / Math.PI;
        this.updateStreak("tilt", Math.abs(angle) > TILT_THRESHOLD_DEGREES);
      } else {
        this.updateStreak("tilt", false);
      }
      roi.delete();
      eyes.delete();
    }

    faces.delete();
    gray.delete();
    src.delete();

    const status: ProctorStatus = this.inAway ? "away" : this.inTilt ? "tilt" : "ok";
    this.onStatus?.(status);
  }

  private updateStreak(kind: ProctorEventType, active: boolean) {
    const isAway = kind === "away";
    const streak = isAway ? this.awayStreak : this.tiltStreak;
    const threshold = isAway ? AWAY_STREAK_TO_FLAG : TILT_STREAK_TO_FLAG;
    const wasIn = isAway ? this.inAway : this.inTilt;

    if (active) {
      const nextStreak = streak + 1;
      if (isAway) this.awayStreak = nextStreak;
      else this.tiltStreak = nextStreak;
      if (nextStreak >= threshold && !wasIn) {
        if (isAway) this.inAway = true;
        else this.inTilt = true;
        this.onEvent(kind);
      }
    } else {
      if (isAway) {
        this.awayStreak = 0;
        this.inAway = false;
      } else {
        this.tiltStreak = 0;
        this.inTilt = false;
      }
    }
  }

  stop() {
    this.stopped = true;
    if (this.timer !== null) window.clearTimeout(this.timer);
    this.faceCascade?.delete?.();
    this.eyeCascade?.delete?.();
  }
}
