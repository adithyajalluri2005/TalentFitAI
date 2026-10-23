import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Bot, Clock, Eye, EyeOff, Gauge, Loader2, MessageSquareText, Mic, MicOff, RotateCcw, Send, SkipForward,
  Sparkles, Square, VideoOff, CircleStop,
  FileText,
} from 'lucide-react';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useToast } from '@/hooks/use-toast';
import { cn } from '@/lib/utils';
import { coachApi, errorMessage, InterviewPrompt, RespondPayload } from '@/services/coach';
import { useEyeContact } from './useEyeContact';
import { SourceLink } from './components';

/** Thinking time before answering, as in one-way video interviews. */
const THINK_SECONDS = 30;
/** Answers past this length are flagged: interviewers expect ~2 minutes. */
const TARGET_SECONDS = 120;

const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.max(0, s) % 60).padStart(2, '0')}`;

/** Microphone loudness 0-1, sampled each animation frame while a stream is given. */
function useAudioLevel(stream: MediaStream | null): number {
  const [level, setLevel] = useState(0);
  useEffect(() => {
    if (!stream?.getAudioTracks().length) {
      setLevel(0);
      return;
    }
    const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const data = new Uint8Array(analyser.frequencyBinCount);
    let raf = 0;
    const tick = () => {
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (const v of data) sum += ((v - 128) / 128) ** 2;
      setLevel(Math.min(1, Math.sqrt(sum / data.length) * 4));
      raf = requestAnimationFrame(tick);
    };
    tick();
    return () => {
      cancelAnimationFrame(raf);
      ctx.close().catch(() => undefined);
    };
  }, [stream]);
  return level;
}

/** Five bars that move with a 0-1 level (or a gentle idle animation when `active` without a level). */
function Bars({ level, active, className }: { level?: number; active: boolean; className?: string }) {
  return (
    <span className={cn('flex h-5 items-end gap-0.5', className)} aria-hidden>
      {[0.5, 0.8, 1, 0.8, 0.5].map((w, i) => (
        <span
          key={i}
          className={cn('w-1 rounded-full bg-current transition-[height] duration-100', active && level === undefined && 'animate-pulse')}
          style={{
            height: active ? `${Math.max(15, (level ?? 0.6) * w * 100)}%` : '15%',
            animationDelay: `${i * 120}ms`,
          }}
        />
      ))}
    </span>
  );
}

/**
 * The final interview, modelled on one-way video interview tools: your camera
 * fills the stage (as the interviewer would see you), the AI interviewer sits
 * in a small tile, and the camera and interviewer voice stay on throughout,
 * as in a real interview. The question shows as a
 * caption, thinking time before you answer, a visible answer timer and a
 * live coach panel (pace, filler words, eye contact). Answers are spoken.
 * Camera frames are analysed in the browser only. Stays mounted across
 * questions so the camera isn't re-opened every turn.
 */
export default function InterviewRoom({ prompt, onSubmit, busy = false }: {
  prompt: InterviewPrompt;
  onSubmit: (p: RespondPayload) => void;
  /** the coach is scoring the last answer / writing the next question */
  busy?: boolean;
}) {
  const { toast } = useToast();
  const onError = useCallback(
    (title: string, e: unknown) => toast({ title, description: errorMessage(e), variant: 'destructive' }),
    [toast],
  );

  // ---------- camera ----------
  const videoRef = useRef<HTMLVideoElement>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [camError, setCamError] = useState<string | null>(null);
  // Until the browser's permission prompt is answered, nothing else should start.
  const [camStarting, setCamStarting] = useState(true);
  const eye = useEyeContact(videoRef, !!stream && stream.getVideoTracks().length > 0);

  const startCamera = useCallback(async () => {
    setCamError(null);
    setCamStarting(true);
    try {
      setStream(await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 }, audio: true }));
      setCamStarting(false);
      return;
    } catch {
      // No camera, or camera blocked: carry on with the microphone only.
    }
    try {
      setStream(await navigator.mediaDevices.getUserMedia({ audio: true }));
      setCamError('No camera available, so this interview continues with audio only and without eye-contact feedback.');
    } catch {
      setCamError('Camera and microphone are blocked. Allow both in the address bar, then try again.');
    }
    setCamStarting(false);
  }, []);

  // The interview starts with the camera on, as a real one would.
  useEffect(() => { startCamera(); }, [startCamera]);

  useEffect(() => {
    if (videoRef.current && stream) videoRef.current.srcObject = stream;
  }, [stream]);
  useEffect(() => () => stream?.getTracks().forEach((t) => t.stop()), [stream]);

  // ---------- interviewer voice ----------
  const [speaking, setSpeaking] = useState(false);

  const speak = useCallback((text: string) => {
    if (!('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 0.98;
    const voices = window.speechSynthesis.getVoices();
    u.voice = voices.find((v) => /en-(IN|GB|US)/.test(v.lang) && /natural|google|microsoft/i.test(v.name))
      ?? voices.find((v) => v.lang.startsWith('en')) ?? null;
    u.onstart = () => setSpeaking(true);
    u.onend = u.onerror = () => setSpeaking(false);
    window.speechSynthesis.speak(u);
  }, []);

  useEffect(() => {
    if (!busy) speak(`${prompt.is_follow_up ? 'Follow-up. ' : ''}${prompt.question}`);
    return () => window.speechSynthesis?.cancel();
  }, [prompt.question, prompt.is_follow_up, busy, speak]);

  // ---------- this question's answer (reset per question) ----------
  const questionKey = `${prompt.turn}-${prompt.question}`;
  const [answer, setAnswer] = useState('');
  const [metrics, setMetrics] = useState<Record<string, number>>({});
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [thinkLeft, setThinkLeft] = useState(THINK_SECONDS);
  const [micStream, setMicStream] = useState<MediaStream | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const ownStream = useRef<MediaStream | null>(null);
  const chunks = useRef<Blob[]>([]);
  const level = useAudioLevel(micStream);

  useEffect(() => {
    setAnswer('');
    setMetrics({});
    setSeconds(0);
    setThinkLeft(THINK_SECONDS);
  }, [questionKey]);

  // Thinking time counts down until the candidate starts answering.
  const thinking = thinkLeft > 0 && !recording && !answer && !busy && !speaking && !camStarting;
  useEffect(() => {
    if (!thinking) return;
    const t = setInterval(() => setThinkLeft((s) => s - 1), 1000);
    return () => clearInterval(t);
  }, [thinking]);

  useEffect(() => {
    if (!recording) return;
    const t = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [recording]);

  useEffect(() => () => ownStream.current?.getTracks().forEach((t) => t.stop()), []);

  const startRecording = async () => {
    try {
      // Reuse the call's microphone if the camera is on; otherwise ask for audio only.
      let audio = stream?.getAudioTracks().length ? new MediaStream(stream.getAudioTracks()) : null;
      if (!audio) {
        audio = await navigator.mediaDevices.getUserMedia({ audio: true });
        ownStream.current = audio;
      }
      const rec = new MediaRecorder(audio);
      chunks.current = [];
      rec.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
      rec.onstop = async () => {
        ownStream.current?.getTracks().forEach((t) => t.stop());
        ownStream.current = null;
        setMicStream(null);
        const camera = eye.snapshot();
        setTranscribing(true);
        try {
          const res = await coachApi.transcribe(new Blob(chunks.current, { type: rec.mimeType || 'audio/webm' }));
          setAnswer((a) => (a ? `${a} ${res.text}` : res.text));
          setMetrics({ ...res.voice_metrics, ...(camera ?? {}) });
        } catch (e) {
          onError('Transcription failed', e);
        } finally {
          setTranscribing(false);
        }
      };
      recorder.current = rec;
      eye.reset();
      rec.start();
      window.speechSynthesis?.cancel();
      setMicStream(audio);
      setSeconds(0);
      setRecording(true);
    } catch (e) {
      onError('Microphone unavailable', e);
    }
  };

  const stopRecording = () => {
    recorder.current?.stop();
    setRecording(false);
  };

  const hasVideo = !!stream && stream.getVideoTracks().length > 0;
  const canSubmit = !!answer.trim() && !recording && !transcribing && !busy;
  const submit = () => canSubmit && onSubmit({ answer, voice_metrics: metrics });
  const over = recording && seconds > TARGET_SECONDS;

  return (
    <div className="space-y-4">
      {/* ---------- progress ---------- */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <div className="flex items-center gap-1.5" aria-label={`Question ${prompt.turn} of ${prompt.of}`}>
          {Array.from({ length: prompt.of }, (_, i) => (
            <span
              key={i}
              className={cn('h-1.5 rounded-full transition-all',
                i + 1 < prompt.turn ? 'w-6 bg-primary' : i + 1 === prompt.turn ? 'w-10 bg-primary' : 'w-6 bg-muted')}
            />
          ))}
        </div>
        <span className="text-sm font-medium tabular-nums">Question {prompt.turn} of {prompt.of}</span>
        <Badge variant="outline">{prompt.skill}</Badge>
        <Badge variant="outline">Difficulty {prompt.difficulty}/5</Badge>
        {prompt.is_follow_up && <Badge variant="secondary">Follow-up</Badge>}
      </div>

      {/* ---------- stage ---------- */}
      <div className="relative overflow-hidden rounded-xl bg-slate-950 text-slate-100 ring-1 ring-border">
        <div className="relative aspect-[4/3] sm:aspect-video">
          {/* candidate camera (primary) */}
          <div className="absolute inset-0 bg-slate-900">
            {hasVideo ? (
              <video ref={videoRef} autoPlay muted playsInline className="h-full w-full object-cover -scale-x-100" />
            ) : (
              <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center text-slate-300">
                <span className="flex h-16 w-16 items-center justify-center rounded-full bg-slate-800"><VideoOff className="h-7 w-7" /></span>
                <p className="max-w-sm text-sm">
                  {camError ?? 'Allow camera and microphone access in your browser\'s prompt to start the interview.'}
                </p>
                {camError && !stream && (
                  <Button size="sm" variant="secondary" onClick={startCamera}><RotateCcw className="h-4 w-4 mr-1.5" /> Try again</Button>
                )}
              </div>
            )}
            <span className="absolute bottom-3 left-3 flex items-center gap-2 rounded-md bg-black/60 px-2 py-1 text-xs">
              You
              {recording && <Bars level={level} active className="h-3 text-emerald-400" />}
            </span>
          </div>

          {/* top-left status chips */}
          <div className="absolute left-3 top-3 flex flex-wrap gap-1.5">
            {hasVideo && eye.status === 'loading' && (
              <span className="flex items-center gap-1.5 rounded-full bg-slate-800/90 px-2.5 py-1 text-xs"><Loader2 className="h-3 w-3 animate-spin" /> Eye tracking</span>
            )}
            {hasVideo && eye.status === 'ready' && (
              <span className={cn('flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium',
                eye.lookingNow ? 'bg-success text-success-foreground' : 'bg-warning text-warning-foreground')}>
                {eye.lookingNow ? <><Eye className="h-3 w-3" /> Eye contact</> : <><EyeOff className="h-3 w-3" /> {eye.faceNow ? 'Look at the camera' : 'Face not visible'}</>}
              </span>
            )}
            {recording && (
              <span className={cn('flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium tabular-nums',
                over ? 'bg-warning text-warning-foreground' : 'bg-destructive text-destructive-foreground')}>
                <span className="h-2 w-2 rounded-full bg-current animate-pulse" /> REC {clock(seconds)} / {clock(TARGET_SECONDS)}
              </span>
            )}
            {thinking && (
              <span className="flex items-center gap-1.5 rounded-full bg-slate-800/90 px-2.5 py-1 text-xs tabular-nums">
                <Clock className="h-3 w-3" /> Thinking time {clock(thinkLeft)}
              </span>
            )}
            {transcribing && (
              <span className="flex items-center gap-1.5 rounded-full bg-slate-800/90 px-2.5 py-1 text-xs">
                <Loader2 className="h-3 w-3 animate-spin" /> Transcribing
              </span>
            )}
          </div>

          {/* AI interviewer (secondary tile) */}
          <div className="absolute right-3 top-3 w-28 sm:w-44 md:w-52 overflow-hidden rounded-lg bg-gradient-to-b from-slate-800 to-slate-900 shadow-lg ring-1 ring-slate-700">
            <div className="flex aspect-video flex-col items-center justify-center gap-1">
              <span className="relative flex h-9 w-9 sm:h-12 sm:w-12 items-center justify-center">
                {speaking && <span className="absolute inset-0 rounded-full bg-primary/40 animate-ping" />}
                <span className={cn('relative flex h-full w-full items-center justify-center rounded-full bg-primary text-primary-foreground ring-2 transition',
                  speaking ? 'ring-primary/70' : 'ring-slate-600')}>
                  <Bot className="h-5 w-5 sm:h-6 sm:w-6" />
                </span>
              </span>
              <span className="flex h-3 items-center text-[10px] text-slate-400">
                {busy ? 'Reviewing…' : speaking ? <Bars active className="h-3 text-primary" /> : recording ? 'Listening…' : thinking ? 'Take a moment' : 'Waiting'}
              </span>
            </div>
            <p className="bg-slate-950/80 px-2 py-0.5 text-[10px] text-slate-300">AI Interviewer</p>
          </div>

          {busy && (
            <div className="absolute inset-0 flex items-center justify-center bg-slate-950/60 backdrop-blur-[1px]">
              <span className="flex items-center gap-2 rounded-full bg-slate-900 px-4 py-2 text-sm">
                <Loader2 className="h-4 w-4 animate-spin text-primary" /> Saving your answer and preparing the next question…
              </span>
            </div>
          )}
        </div>

        {/* question caption */}
        <div className="border-t border-slate-800 bg-slate-900 px-4 py-3 sm:px-5 sm:py-4">
          <div className="flex items-start gap-3">
            <MessageSquareText className="mt-1 h-4 w-4 shrink-0 text-primary" />
            <div className="min-w-0 flex-1 space-y-1">
              <p className="text-base sm:text-lg font-semibold leading-snug">{prompt.question}</p>
              {!prompt.is_follow_up && (
                prompt.kind === 'intro' || prompt.kind === 'resume' ? (
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-700 bg-slate-800/80 px-2.5 py-1 text-[11px] text-slate-300">
                    <FileText className="h-3 w-3" /> {prompt.kind === 'intro' ? 'Opening question' : 'Based on your resume'}
                  </span>
                ) : (
                  <SourceLink name={prompt.source_name} url={prompt.source_url} label="Question based on" tone="dark" />
                )
              )}
            </div>
          </div>
        </div>

        {/* control bar */}
        <div className="flex flex-wrap items-center justify-center gap-2 sm:gap-3 border-t border-slate-800 bg-slate-950 px-3 py-3">
          <RoundButton label="Ask the interviewer to repeat the question" onClick={() => speak(prompt.question)} disabled={busy || recording}>
            <RotateCcw className="h-5 w-5" />
          </RoundButton>

          {recording ? (
            <Button onClick={stopRecording} className="h-12 rounded-full px-6 bg-destructive text-destructive-foreground hover:bg-destructive/90">
              <Square className="h-4 w-4 mr-2 fill-current" /> Stop · {clock(seconds)}
            </Button>
          ) : (
            <Button onClick={startRecording} disabled={busy || transcribing || camStarting} className="h-12 rounded-full px-6">
              <Mic className="h-5 w-5 mr-2" /> {answer ? 'Record more' : thinking ? 'Start answering' : 'Record answer'}
            </Button>
          )}

          <Button onClick={submit} disabled={!canSubmit} variant="secondary" className="h-12 rounded-full px-5">
            <Send className="h-4 w-4 mr-2" /> Submit
          </Button>

          <Button
            onClick={() => onSubmit({ action: 'skip' })}
            disabled={busy || recording || transcribing}
            variant="ghost"
            title="Skip this question. It counts as unanswered."
            className="h-12 rounded-full px-5 text-slate-300 hover:text-white hover:bg-slate-800"
          >
            <SkipForward className="h-4 w-4 mr-2" /> Skip
          </Button>

          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button
                disabled={busy || recording || transcribing}
                variant="ghost"
                className="h-12 rounded-full px-5 text-red-300 hover:text-white hover:bg-red-900/60"
              >
                <CircleStop className="h-4 w-4 mr-2" /> End interview
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>End the interview now?</AlertDialogTitle>
                <AlertDialogDescription>
                  Your answers so far will be scored and your readiness re-scored. This question and any
                  remaining ones won't be asked. There is one interview per session, so you can't resume it.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Keep going</AlertDialogCancel>
                <AlertDialogAction
                  onClick={() => onSubmit({ action: 'end' })}
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                >
                  End interview
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </div>

      {/* ---------- live coach ---------- */}
      <LiveCoach recording={recording} seconds={seconds} eye={eye} cameraOn={hasVideo} cameraStarting={camStarting} metrics={metrics} />

      <p className="text-xs text-muted-foreground">
        Your camera is analysed in this browser only. No video is uploaded or stored; only your spoken answer's audio is sent for transcription.
      </p>
    </div>
  );
}

function RoundButton({ label, onClick, disabled, children }: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      className={cn(
        'flex h-12 w-12 items-center justify-center rounded-full bg-slate-800 text-slate-100 transition-colors hover:bg-slate-700',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-40',
      )}
    >
      {children}
    </button>
  );
}

type Tone = 'good' | 'warn' | 'idle';
const TONE: Record<Tone, string> = {
  good: 'text-success',
  warn: 'text-warning',
  idle: 'text-muted-foreground',
};

/** Live nudges while answering, then the delivery numbers once the answer is transcribed. */
function LiveCoach({ recording, seconds, eye, cameraOn, cameraStarting, metrics }: {
  recording: boolean;
  seconds: number;
  eye: ReturnType<typeof useEyeContact>;
  cameraOn: boolean;
  cameraStarting: boolean;
  metrics: Record<string, number>;
}) {
  const has = metrics.duration_seconds > 0;
  const wpm = Math.round(metrics.words_per_minute ?? 0);
  const rows: { icon: typeof Gauge; label: string; value: string; tone: Tone; hint: string }[] = [
    {
      icon: Clock, label: 'Length',
      value: recording ? clock(seconds) : has ? clock(Math.round(metrics.duration_seconds)) : '—',
      tone: (recording ? seconds : metrics.duration_seconds ?? 0) > TARGET_SECONDS ? 'warn'
        : recording || has ? 'good' : 'idle',
      hint: 'about 2:00',
    },
    {
      icon: Gauge, label: 'Pace',
      value: has ? `${wpm} wpm` : '—',
      tone: !has ? 'idle' : wpm >= 110 && wpm <= 170 ? 'good' : 'warn',
      hint: '120–160 wpm',
    },
    {
      icon: Sparkles, label: 'Filler words',
      value: has ? String(metrics.filler_words ?? 0) : '—',
      tone: !has ? 'idle' : (metrics.filler_words ?? 0) <= 3 ? 'good' : 'warn',
      hint: 'um, like, basically',
    },
    {
      icon: Eye, label: 'Eye contact',
      value: metrics.eye_contact_pct !== undefined ? `${metrics.eye_contact_pct}%`
        : recording && cameraOn && eye.status === 'ready' ? (eye.lookingNow ? 'Good' : 'Look up') : cameraOn || cameraStarting ? '—' : 'No camera',
      tone: metrics.eye_contact_pct !== undefined ? (metrics.eye_contact_pct >= 60 ? 'good' : 'warn')
        : recording && eye.status === 'ready' ? (eye.lookingNow ? 'good' : 'warn') : 'idle',
      hint: 'look at the camera',
    },
  ];
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          {recording ? <Mic className="h-4 w-4 text-destructive" /> : <MicOff className="h-4 w-4 text-muted-foreground" />}
          Live coach
        </CardTitle>
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {rows.map((r) => (
          <div key={r.label} className="min-w-0 rounded-lg border p-3">
            <p className="flex items-center gap-1.5 text-xs font-medium">
              <r.icon className={cn('h-3.5 w-3.5 shrink-0', TONE[r.tone])} /> {r.label}
            </p>
            <p className={cn('mt-1 truncate text-lg font-semibold tabular-nums', TONE[r.tone])}>{r.value}</p>
            <p className="truncate text-[11px] text-muted-foreground">{r.hint}</p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
