import { useCallback, useEffect, useRef, useState } from 'react';
import type { FaceLandmarker } from '@mediapipe/tasks-vision';

// MediaPipe runs entirely in the browser: frames are analysed locally and
// never uploaded. The wasm runtime and model are fetched once from public CDNs.
const WASM_BASE = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.21/wasm';
const MODEL_URL =
  'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task';
const SAMPLE_MS = 200; // ~5 checks per second is plenty for a percentage

// Face-mesh landmark indexes
const NOSE_TIP = 1;
const LEFT_CHEEK = 234;
const RIGHT_CHEEK = 454;
const FOREHEAD = 10;
const CHIN = 152;

export interface EyeContactStats {
  eye_contact_pct: number;
  face_visible_pct: number;
}

let landmarkerPromise: Promise<FaceLandmarker> | null = null;

function loadLandmarker(): Promise<FaceLandmarker> {
  // Lazy and shared: the ~3 MB model only loads when a camera interview starts.
  landmarkerPromise ??= import('@mediapipe/tasks-vision').then(async ({ FaceLandmarker, FilesetResolver }) => {
    const fileset = await FilesetResolver.forVisionTasks(WASM_BASE);
    return FaceLandmarker.createFromOptions(fileset, {
      baseOptions: { modelAssetPath: MODEL_URL, delegate: 'GPU' },
      runningMode: 'VIDEO',
      numFaces: 1,
      outputFaceBlendshapes: true,
    });
  });
  landmarkerPromise.catch(() => { landmarkerPromise = null; });
  return landmarkerPromise;
}

/**
 * "Looking at the camera" = head roughly facing the screen (nose centred
 * between the cheeks and between forehead and chin) and eyes not turned away
 * (MediaPipe's eyeLook* blendshapes). A practical proxy, not a gaze tracker.
 */
function isLookingAtCamera(result: ReturnType<FaceLandmarker['detectForVideo']>): boolean {
  const lm = result.faceLandmarks?.[0];
  if (!lm) return false;
  const width = lm[RIGHT_CHEEK].x - lm[LEFT_CHEEK].x;
  const height = lm[CHIN].y - lm[FOREHEAD].y;
  if (Math.abs(width) < 1e-3 || Math.abs(height) < 1e-3) return false;
  const yaw = (lm[NOSE_TIP].x - (lm[LEFT_CHEEK].x + lm[RIGHT_CHEEK].x) / 2) / Math.abs(width);
  const pitch = (lm[NOSE_TIP].y - lm[FOREHEAD].y) / height; // ~0.55-0.65 when facing forward
  const headForward = Math.abs(yaw) < 0.12 && pitch > 0.45 && pitch < 0.75;

  const shapes = Object.fromEntries((result.faceBlendshapes?.[0]?.categories ?? []).map((c) => [c.categoryName, c.score]));
  const eyesAway = Math.max(
    shapes.eyeLookOutLeft ?? 0, shapes.eyeLookOutRight ?? 0,
    shapes.eyeLookInLeft ?? 0, shapes.eyeLookInRight ?? 0,
    shapes.eyeLookUpLeft ?? 0, shapes.eyeLookDownLeft ?? 0,
  ) > 0.55;
  return headForward && !eyesAway;
}

/** Tracks face presence and eye contact on a playing <video> while `active`. */
export function useEyeContact(videoRef: React.RefObject<HTMLVideoElement>, active: boolean) {
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [lookingNow, setLookingNow] = useState(false);
  const [faceNow, setFaceNow] = useState(false);
  const counts = useRef({ frames: 0, face: 0, looking: 0 });

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    let timer: number | undefined;
    setStatus('loading');
    loadLandmarker()
      .then((landmarker) => {
        if (cancelled) return;
        setStatus('ready');
        let lastTs = 0;
        timer = window.setInterval(() => {
          const video = videoRef.current;
          if (!video || video.readyState < 2 || video.videoWidth === 0) return;
          const ts = Math.max(performance.now(), lastTs + 1); // timestamps must increase
          lastTs = ts;
          try {
            const result = landmarker.detectForVideo(video, ts);
            const face = (result.faceLandmarks?.length ?? 0) > 0;
            const looking = face && isLookingAtCamera(result);
            counts.current.frames += 1;
            if (face) counts.current.face += 1;
            if (looking) counts.current.looking += 1;
            setFaceNow(face);
            setLookingNow(looking);
          } catch {
            /* a dropped frame is fine */
          }
        }, SAMPLE_MS);
      })
      .catch(() => !cancelled && setStatus('error'));
    return () => {
      cancelled = true;
      if (timer) window.clearInterval(timer);
    };
  }, [active, videoRef]);

  /** Start a fresh measurement window (e.g. when recording an answer starts). */
  const reset = useCallback(() => { counts.current = { frames: 0, face: 0, looking: 0 }; }, []);

  /** Percentages since the last reset, or null if nothing was measured. */
  const snapshot = useCallback((): EyeContactStats | null => {
    const { frames, face, looking } = counts.current;
    if (frames < 5) return null;
    return {
      eye_contact_pct: Math.round((looking / frames) * 100),
      face_visible_pct: Math.round((face / frames) * 100),
    };
  }, []);

  return { status, lookingNow, faceNow, reset, snapshot };
}
