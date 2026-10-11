import { useCallback, useEffect, useRef, useState } from 'react';
import { Bot, Eye, EyeOff, Loader2, Mic, Square, Video, VideoOff, Volume2, VolumeX } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/hooks/use-toast';
import { cn } from '@/lib/utils';
import { coachApi, errorMessage, InterviewPrompt, RespondPayload } from '@/services/coach';
import { useEyeContact } from './useEyeContact';

const VOICE_KEY = 'talentfit-interviewer-voice';

function readVoicePref(): boolean {
  try {
    return localStorage.getItem(VOICE_KEY) !== 'off';
  } catch {
    return true;
  }
}

/**
 * The final interview as a video call: an interviewer who speaks each
 * question, your camera with live eye-contact feedback, and a recorder whose
 * audio goes to Whisper. Camera frames are analysed in the browser only.
 * Stays mounted across questions so the camera isn't re-opened every turn.
 */
export default function InterviewRoom({ prompt, onSubmit, busy = false }: {
  prompt: InterviewPrompt;
  onSubmit: (p: RespondPayload) => void;
  /** the coach is scoring the last answer / writing the next question */
  busy?: boolean;
}) {
  const { toast } = useToast();
  const videoRef = useRef<HTMLVideoElement>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [camError, setCamError] = useState<string | null>(null);
  const [voiceOn, setVoiceOn] = useState(readVoicePref);
  const [speaking, setSpeaking] = useState(false);
  const eye = useEyeContact(videoRef, !!stream && stream.getVideoTracks().length > 0);

  // ---------- camera ----------
  const startCamera = useCallback(async () => {
    setCamError(null);
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 }, audio: true });
      setStream(s);
    } catch {
      setCamError('Camera or microphone blocked. Allow access in the address bar, or answer by typing.');
    }
  }, []);

  const stopCamera = useCallback(() => {
    setStream((s) => {
      s?.getTracks().forEach((t) => t.stop());
      return null;
    });
  }, []);

  useEffect(() => {
    if (videoRef.current && stream) videoRef.current.srcObject = stream;
  }, [stream]);

  useEffect(() => () => stream?.getTracks().forEach((t) => t.stop()), [stream]);

  // ---------- interviewer voice ----------
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
    if (voiceOn) speak(`${prompt.is_follow_up ? 'Follow-up. ' : ''}${prompt.question}`);
    return () => window.speechSynthesis?.cancel();
  }, [prompt.question, prompt.is_follow_up, voiceOn, speak]);

  const toggleVoice = () => {
    setVoiceOn((v) => {
      try { localStorage.setItem(VOICE_KEY, v ? 'off' : 'on'); } catch { /* per-visit only */ }
      if (v) window.speechSynthesis?.cancel();
      return !v;
    });
  };

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2">
        {/* interviewer */}
        <Card className="overflow-hidden">
          <div className="relative aspect-video bg-gradient-to-br from-primary/90 to-primary flex flex-col items-center justify-center text-primary-foreground">
            <span className={cn('flex h-20 w-20 items-center justify-center rounded-full bg-primary-foreground/15 ring-4 ring-primary-foreground/20 transition-transform',
              speaking && 'animate-pulse scale-105')}>
              <Bot className="h-10 w-10" />
            </span>
            <p className="mt-3 text-sm font-medium">AI Interviewer</p>
            <p className="text-xs opacity-80">{speaking ? 'Speaking…' : 'Listening'}</p>
            <Button
              size="sm" variant="secondary"
              className="absolute bottom-3 right-3 h-8"
              onClick={toggleVoice}
              aria-label={voiceOn ? 'Mute interviewer voice' : 'Unmute interviewer voice'}
            >
              {voiceOn ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
            </Button>
          </div>
        </Card>

        {/* candidate camera */}
        <Card className="overflow-hidden">
          <div className="relative aspect-video bg-muted flex items-center justify-center">
            {stream ? (
              <>
                <video ref={videoRef} autoPlay muted playsInline className="h-full w-full object-cover -scale-x-100" />
                <div className="absolute left-3 top-3 flex flex-wrap gap-1.5">
                  {eye.status === 'loading' && <Badge variant="secondary"><Loader2 className="h-3 w-3 mr-1 animate-spin" /> Starting eye tracking</Badge>}
                  {eye.status === 'ready' && (
                    eye.lookingNow ? (
                      <Badge className="bg-success text-success-foreground hover:bg-success"><Eye className="h-3 w-3 mr-1" /> Eye contact</Badge>
                    ) : (
                      <Badge className="bg-warning text-warning-foreground hover:bg-warning">
                        <EyeOff className="h-3 w-3 mr-1" /> {eye.faceNow ? 'Look at the camera' : 'Face not visible'}
                      </Badge>
                    )
                  )}
                  {eye.status === 'error' && <Badge variant="secondary">Eye tracking unavailable</Badge>}
                </div>
                <Button size="sm" variant="secondary" className="absolute bottom-3 right-3 h-8" onClick={stopCamera} aria-label="Turn camera off">
                  <VideoOff className="h-4 w-4" />
                </Button>
              </>
            ) : (
              <div className="p-6 text-center space-y-3">
                <Video className="h-8 w-8 mx-auto text-muted-foreground" />
                <p className="text-sm text-muted-foreground">Turn on your camera for a realistic interview with eye-contact feedback.</p>
                <Button size="sm" onClick={startCamera}><Video className="h-4 w-4 mr-1.5" /> Turn on camera</Button>
                {camError && <p className="text-xs text-destructive">{camError}</p>}
              </div>
            )}
          </div>
        </Card>
      </div>
      <p className="text-xs text-muted-foreground">
        Your camera is analysed in this browser only — no video is uploaded or stored. Only your spoken answer's audio is sent for transcription.
      </p>

      {busy ? (
        <Card><CardContent className="py-12 flex flex-col items-center gap-3 text-muted-foreground">
          <Loader2 className="h-7 w-7 animate-spin text-primary" />
          <span>The interviewer is reviewing your answer…</span>
        </CardContent></Card>
      ) : (
      <AnswerPanel
        key={`${prompt.turn}-${prompt.question}`}
        prompt={prompt}
        stream={stream}
        eye={eye}
        onReplay={() => speak(prompt.question)}
        onSubmit={onSubmit}
        onError={(title, e) => toast({ title, description: errorMessage(e), variant: 'destructive' })}
      />
      )}
    </div>
  );
}

/** One question: record (or type) an answer and submit it. Remounts per question. */
function AnswerPanel({ prompt, stream, eye, onReplay, onSubmit, onError }: {
  prompt: InterviewPrompt;
  stream: MediaStream | null;
  eye: ReturnType<typeof useEyeContact>;
  onReplay: () => void;
  onSubmit: (p: RespondPayload) => void;
  onError: (title: string, e: unknown) => void;
}) {
  const [answer, setAnswer] = useState('');
  const [metrics, setMetrics] = useState<Record<string, number>>({});
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const recorder = useRef<MediaRecorder | null>(null);
  const ownStream = useRef<MediaStream | null>(null);
  const chunks = useRef<Blob[]>([]);

  useEffect(() => {
    if (!recording) return;
    const t = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [recording]);

  useEffect(() => () => ownStream.current?.getTracks().forEach((t) => t.stop()), []);

  const start = async () => {
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
      setSeconds(0);
      setRecording(true);
    } catch (e) {
      onError('Microphone unavailable', e);
    }
  };

  const stop = () => {
    recorder.current?.stop();
    setRecording(false);
  };

  return (
    <Card className="border-primary/40">
      <CardContent className="pt-6 space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge>Final interview</Badge>
          <span className="text-sm text-muted-foreground">Question {prompt.turn} of {prompt.of}</span>
          <Badge variant="outline">{prompt.skill}</Badge>
          <Badge variant="outline">Difficulty {prompt.difficulty}/5</Badge>
          {prompt.is_follow_up && <Badge variant="secondary">Follow-up</Badge>}
        </div>
        <div className="flex items-start gap-2">
          <p className="text-lg font-semibold leading-snug flex-1">{prompt.question}</p>
          <Button variant="ghost" size="sm" className="h-8 w-8 p-0 shrink-0" onClick={onReplay} aria-label="Hear the question again">
            <Volume2 className="h-4 w-4" />
          </Button>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {recording ? (
            <Button variant="destructive" onClick={stop}>
              <Square className="h-4 w-4 mr-2" /> Stop · {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')}
            </Button>
          ) : (
            <Button variant="secondary" onClick={start} disabled={transcribing}>
              <Mic className="h-4 w-4 mr-2" /> {answer ? 'Record more' : 'Record answer'}
            </Button>
          )}
          {recording && <span className="h-2.5 w-2.5 rounded-full bg-destructive animate-pulse" aria-label="Recording" />}
          {transcribing && <span className="text-sm text-muted-foreground flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" /> Transcribing…</span>}
        </div>

        <Textarea rows={5} placeholder="Your answer…" value={answer} onChange={(e) => setAnswer(e.target.value)} />

        {(metrics.duration_seconds > 0 || metrics.eye_contact_pct !== undefined) && (
          <div className="flex flex-wrap gap-2 text-xs">
            {metrics.duration_seconds > 0 && (
              <>
                <Badge variant="outline" className="font-normal">{Math.round(metrics.words_per_minute)} words/min</Badge>
                <Badge variant="outline" className="font-normal">{metrics.filler_words} filler words</Badge>
                <Badge variant="outline" className="font-normal">{Math.round(metrics.duration_seconds)}s</Badge>
              </>
            )}
            {metrics.eye_contact_pct !== undefined && (
              <Badge variant="outline" className={cn('font-normal', metrics.eye_contact_pct >= 60 ? 'text-success' : 'text-warning')}>
                <Eye className="h-3 w-3 mr-1" /> {metrics.eye_contact_pct}% eye contact
              </Badge>
            )}
          </div>
        )}

        <div className="flex justify-end">
          <Button disabled={!answer.trim() || recording || transcribing} onClick={() => onSubmit({ answer, voice_metrics: metrics })}>
            Submit answer
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
