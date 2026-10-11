import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { CheckCircle2, Loader2, MessageSquareQuote, Trophy, TrendingUp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Label } from '@/components/ui/label';
import { useToast } from '@/hooks/use-toast';
import {
  coachApi, errorMessage, CheckpointPrompt, InterviewTurn, RespondPayload, SessionView,
} from '@/services/coach';
import { ReadinessRing, SkillRow } from './components';
import SkillGapView from './SkillGapView';
import InterviewRoom from './InterviewRoom';
import { cn } from '@/lib/utils';

type Tab = 'plan' | 'checkpoints' | 'interview';

const TAB_TITLE: Record<Tab, string> = {
  plan: 'Skill Gap Analysis',
  checkpoints: 'Skill Assessments',
  interview: 'Final Interview',
};

/** Which tab the session's current step lives on. */
function tabFor(view: SessionView): Tab {
  if (view.waiting_for?.type === 'checkpoint') return 'checkpoints';
  if (view.waiting_for?.type === 'interview_question') return 'interview';
  return 'plan';
}

export default function Session() {
  const { threadId = '', tab: rawTab } = useParams();
  const tab: Tab = rawTab === 'checkpoints' || rawTab === 'interview' ? rawTab : 'plan';
  const navigate = useNavigate();
  const { toast } = useToast();
  const [view, setView] = useState<SessionView | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [refreshing, setRefreshing] = useState(false);
  const [forceQuiz, setForceQuiz] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const v = await coachApi.session(threadId);
        if (cancelled) return;
        setView(v);
        // Sessions saved in the older weekly-plan format have skills but no
        // topics; rebuild them in place (progress and the pending step are kept).
        const legacy = v.state.plan.length > 0 && v.state.plan.every((p) => !p.topics?.length);
        if (legacy && !v.done) {
          setRefreshing(true);
          try {
            const refreshed = await coachApi.refreshPlan(threadId);
            if (!cancelled) setView(refreshed);
          } catch (e) {
            if (!cancelled) toast({ title: 'Could not load study topics', description: errorMessage(e), variant: 'destructive' });
          } finally {
            if (!cancelled) setRefreshing(false);
          }
        }
      } catch (e) {
        if (!cancelled) setLoadError(errorMessage(e));
      }
    })();
    return () => { cancelled = true; };
  }, [threadId, toast]);

  const respond = useCallback(async (payload: RespondPayload) => {
    setBusy(true);
    try {
      const before = view?.state.history.length ?? 0;
      const next = await coachApi.respond(threadId, payload);
      setView(next);
      // A finished cycle shows its recap on the plan tab; otherwise follow the
      // graph to wherever it is now waiting.
      const target = next.state.history.length > before ? 'plan' : tabFor(next);
      if (target !== tab) navigate(`/session/${threadId}/${target}`);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (e) {
      toast({ title: 'Something went wrong', description: errorMessage(e), variant: 'destructive' });
    } finally {
      setBusy(false);
    }
  }, [threadId, toast, view, tab, navigate]);

  const tickTopic = useCallback(async (skill: string, index: number, done: boolean) => {
    // Optimistic: the checkbox flips at once; the server copy wins when it answers.
    setView((v) => v && { ...v, topic_done: applyTick(v.topic_done ?? {}, skill, index, done) });
    try {
      const r = await coachApi.tickTopic(threadId, skill, index, done);
      setView((v) => v && { ...v, topic_done: r.topic_done });
    } catch (e) {
      toast({ title: 'Could not save that tick', description: errorMessage(e), variant: 'destructive' });
      coachApi.session(threadId).then(setView).catch(() => undefined);
    }
  }, [threadId, toast]);

  if (loadError) {
    return (
      <div className="max-w-md mx-auto py-24 text-center space-y-4">
        <p className="text-destructive">{loadError}</p>
        <Button asChild variant="outline"><Link to="/start">Start a new session</Link></Button>
      </div>
    );
  }
  if (!view) return <div className="py-24 flex justify-center"><Loader2 className="h-8 w-8 animate-spin text-primary" /></div>;

  const { state, waiting_for: waiting } = view;
  const lastSnapshot = state.history[state.history.length - 1];
  const turnsThisCycle = state.interview.slice(state.cycle * state.interview_turns);
  const answered = turnsThisCycle.filter((t) => t.score);
  const lastAnswered = answered[answered.length - 1];
  const showCycleRecap = !!lastSnapshot && (view.done || turnsThisCycle.length === 0);
  const goTo = (t: Tab) => navigate(`/session/${threadId}/${t}`);
  const topicsFor = (skill: string) => state.plan.find((p) => p.skill === skill)?.topics.length ?? 0;
  const isReady = (skill: string) => (view.topic_done?.[skill]?.length ?? 0) >= topicsFor(skill);
  // Open this skill's assessment; if another skill's quiz is pending, switch to this one first.
  const assess = (skill: string) => {
    // Go to the Assessments tab first so its "thinking" state shows while a new quiz is written.
    goTo('checkpoints');
    if (!(waiting?.type === 'checkpoint' && waiting.skill === skill)) respond({ action: 'switch', skill });
  };

  const thinking = (
    <Card><CardContent className="py-16 flex flex-col items-center gap-3 text-muted-foreground">
      <Loader2 className="h-8 w-8 animate-spin text-primary" />
      <span>Your coach is thinking…</span>
    </CardContent></Card>
  );

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_340px] gap-6 pb-12">
      {/* ---------- main column ---------- */}
      <div className="space-y-6 min-w-0">
        <div>
          <h1 className="text-2xl font-bold text-foreground">{TAB_TITLE[tab]}</h1>
          <div className="text-muted-foreground mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="font-medium text-foreground">{state.target_role}</span>
            <span aria-hidden>·</span>
            <span>Cycle {state.cycle + 1} of {state.max_cycles}</span>
            <Badge variant="secondary" className="font-normal">{statusLabel(view)}</Badge>
          </div>
        </div>

        {tab === 'plan' && (
          <>
            {showCycleRecap && <CycleRecap view={view} />}
            {refreshing ? (
              <Card><CardContent className="py-16 flex flex-col items-center gap-3 text-muted-foreground text-sm">
                <Loader2 className="h-6 w-6 animate-spin text-primary" />
                Finding topics and the best sources for each skill… (about a minute)
              </CardContent></Card>
            ) : (
              <SkillGapView
                view={view}
                onTick={view.done ? undefined : tickTopic}
                onAssess={view.done ? undefined : assess}
                onInterview={() => goTo('interview')}
              />
            )}
          </>
        )}

        {tab === 'checkpoints' && (
          busy ? thinking : waiting?.type === 'checkpoint' ? (
            isReady(waiting.skill) ? (
              <>
                <QuizPanel key={`${state.cycle}-${waiting.skill}`} prompt={waiting} onSubmit={respond} />
                {state.checkpoints.length > 0 && <LastCheckpoint result={state.checkpoints[state.checkpoints.length - 1]} />}
              </>
            ) : (
              <AssessmentGate
                pending={waiting.pending ?? [waiting.skill]}
                current={waiting.skill}
                progress={(sk) => [view.topic_done?.[sk]?.length ?? 0, topicsFor(sk)]}
                onAssess={assess}
                onStudy={() => goTo('plan')}
                onTakeAnyway={() => setForceQuiz(waiting.skill)}
                onSkipAll={() => respond({ action: 'skip_all' })}
                forced={forceQuiz === waiting.skill}
                quiz={<QuizPanel key={`${state.cycle}-${waiting.skill}`} prompt={waiting} onSubmit={respond} />}
              />
            )
          ) : (
            <Placeholder
              text={view.done ? 'This coaching session is complete.' : 'All skill assessments for this cycle are done.'}
              action={!view.done && waiting?.type === 'interview_question' ? { label: 'Start final interview', onClick: () => goTo('interview') } : undefined}
            />
          )
        )}

        {tab === 'interview' && (
          waiting?.type === 'interview_question' ? (
            // Kept mounted while the coach thinks, so the camera stays on between questions.
            <>
              {lastAnswered && !busy && <TurnFeedback turn={lastAnswered} />}
              <InterviewRoom prompt={waiting} onSubmit={respond} busy={busy} />
            </>
          ) : busy ? thinking : waiting?.type === 'checkpoint' ? (
            <Placeholder
              text="The final interview opens after every skill assessment. Finish your topics and assessments first, or skip straight to the interview."
              action={{ label: 'Go to Skill Gap & Topics', onClick: () => goTo('plan') }}
              secondary={{ label: 'Skip to interview', onClick: () => respond({ action: 'skip_all' }) }}
            />
          ) : (
            <Placeholder text="This coaching session is complete." action={{ label: 'See results', onClick: () => goTo('plan') }} />
          )
        )}
      </div>

      {/* ---------- side column ---------- */}
      <aside className="space-y-6 lg:sticky lg:top-6 self-start">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-base">Readiness</CardTitle></CardHeader>
          <CardContent className="flex flex-col items-center gap-2">
            <ReadinessRing value={view.readiness} target={state.target_readiness} />
            {state.history.length > 0 && (
              <p className="text-xs text-muted-foreground">
                Re-scores: {state.history.map((h) => `${Math.round(h.readiness)}%`).join(' → ')}
              </p>
            )}
            <Button variant="ghost" size="sm" asChild>
              <Link to="/dashboard"><TrendingUp className="h-4 w-4 mr-1" /> Progress over time</Link>
            </Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Skills</CardTitle>
            <CardDescription className="text-xs">Bar = your level · line = role requirement. Tap a skill to see the evidence.</CardDescription>
          </CardHeader>
          <CardContent className="divide-y divide-border">
            {state.skills.map((s) => <SkillRow key={s.skill} skill={s} />)}
          </CardContent>
        </Card>
      </aside>
    </div>
  );
}

function Placeholder({ text, action, secondary }: {
  text: string;
  action?: { label: string; onClick: () => void };
  secondary?: { label: string; onClick: () => void };
}) {
  return (
    <Card>
      <CardContent className="py-12 flex flex-col items-center gap-4 text-center">
        <p className="text-muted-foreground max-w-md">{text}</p>
        {(action || secondary) && (
          <div className="flex flex-wrap gap-2 justify-center">
            {secondary && <Button variant="outline" onClick={secondary.onClick}>{secondary.label}</Button>}
            {action && <Button onClick={action.onClick}>{action.label}</Button>}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function statusLabel(view: SessionView): string {
  if (view.state.status === 'ready') return 'Interview-ready 🎉';
  if (view.done) return 'Coaching complete';
  const w = view.waiting_for;
  if (w?.type === 'checkpoint') return `Next: ${w.skill} assessment`;
  if (w?.type === 'interview_question') return `Next: interview question ${w.turn} of ${w.of}`;
  return 'Working…';
}

// ---------------- checkpoint quiz ----------------

function QuizPanel({ prompt, onSubmit }: { prompt: CheckpointPrompt; onSubmit: (p: RespondPayload) => void }) {
  const [answers, setAnswers] = useState<(number | undefined)[]>(() => prompt.questions.map(() => undefined));
  const complete = answers.every((a) => a !== undefined);
  return (
    <Card className="border-primary/40">
      <CardHeader>
        <div className="flex items-center gap-2"><Badge>Skill assessment</Badge><span className="text-sm text-muted-foreground">{prompt.skill}</span></div>
        <CardTitle className="text-lg mt-2">{prompt.skill} assessment</CardTitle>
        <CardDescription>
          Study the {prompt.skill} topics first — come back any time; your session is saved.
          When you're ready, answer these to update your score.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {prompt.questions.map((q, i) => (
          <div key={i} className="space-y-2">
            <p className="font-medium text-sm">{i + 1}. {q.question}</p>
            <RadioGroup
              value={answers[i] !== undefined ? String(answers[i]) : ''}
              onValueChange={(v) => setAnswers((a) => a.map((x, j) => (j === i ? Number(v) : x)))}
            >
              {q.options.map((o, j) => (
                <div key={j} className="flex items-start gap-2">
                  <RadioGroupItem value={String(j)} id={`q${i}o${j}`} className="mt-0.5" />
                  <Label htmlFor={`q${i}o${j}`} className="font-normal text-sm leading-snug cursor-pointer">{o}</Label>
                </div>
              ))}
            </RadioGroup>
          </div>
        ))}
        <div className="flex flex-wrap gap-2 justify-end pt-2">
          <Button variant="ghost" onClick={() => onSubmit({ action: 'skip_all' })}>Skip to mock interview</Button>
          <Button variant="outline" onClick={() => onSubmit({ action: 'skip' })}>Skip this checkpoint</Button>
          <Button disabled={!complete} onClick={() => onSubmit({ answers: answers as number[] })}>Submit answers</Button>
        </div>
      </CardContent>
    </Card>
  );
}

function LastCheckpoint({ result }: { result: SessionView['state']['checkpoints'][number] }) {
  if (result.skipped) return null;
  const pct = Math.round(result.score * 100);
  return (
    <p className="text-sm text-muted-foreground flex items-center gap-2">
      <CheckCircle2 className={cn('h-4 w-4', pct >= 75 ? 'text-success' : 'text-warning')} />
      Last checkpoint — {result.skill}: {pct}% correct. Your skill level was updated.
    </p>
  );
}

function TurnFeedback({ turn }: { turn: InterviewTurn }) {
  const s = turn.score!;
  return (
    <Card className="bg-muted/40">
      <CardContent className="pt-5 space-y-2">
        <div className="flex items-center gap-2 text-sm font-medium">
          <MessageSquareQuote className="h-4 w-4 text-primary" /> Feedback on your last answer
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <Badge variant="outline">Correctness {s.correctness}/5</Badge>
          <Badge variant="outline">Depth {s.depth}/5</Badge>
          <Badge variant="outline">Communication {s.communication}/5</Badge>
        </div>
        <p className="text-sm">{turn.feedback}</p>
        {turn.needs_follow_up && !turn.is_follow_up && (
          <p className="text-xs text-muted-foreground">Your coach will probe this point with a follow-up.</p>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------- end of cycle ----------------

function CycleRecap({ view }: { view: SessionView }) {
  const { state } = view;
  const h = state.history;
  const last = h[h.length - 1];
  const prev = h.length > 1 ? h[h.length - 2] : null;
  const ready = state.status === 'ready';
  const lastCycleTurns = state.interview.slice(last.cycle * state.interview_turns, (last.cycle + 1) * state.interview_turns);
  return (
    <Card className={cn(ready ? 'border-success' : 'border-primary/40')}>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          {ready ? <Trophy className="h-5 w-5 text-success" /> : <TrendingUp className="h-5 w-5 text-primary" />}
          {ready ? 'You are interview-ready!' : view.done ? 'Coaching complete' : `Cycle ${last.cycle + 1} results`}
        </CardTitle>
        <CardDescription>
          Readiness {Math.round(last.readiness)}%{prev && ` (${last.readiness >= prev.readiness ? '+' : ''}${Math.round(last.readiness - prev.readiness)} since last cycle)`}
          {!view.done && ' — your plan has been updated for the next cycle.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm">{state.summary}</p>
        {state.next_steps.length > 0 && (
          <div>
            <p className="text-sm font-medium mb-1">Next steps</p>
            <ul className="list-disc list-inside text-sm text-muted-foreground space-y-0.5">
              {state.next_steps.map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          </div>
        )}
        {lastCycleTurns.length > 0 && (
          <details className="text-sm">
            <summary className="cursor-pointer font-medium">Interview review ({lastCycleTurns.length} answers)</summary>
            <div className="mt-3 space-y-4">
              {lastCycleTurns.map((t, i) => (
                <div key={i} className="space-y-1">
                  <p className="font-medium">{t.question}</p>
                  <p className="text-muted-foreground italic">“{t.answer}”</p>
                  {t.score && (
                    <p className="text-xs">Correctness {t.score.correctness} · Depth {t.score.depth} · Communication {t.score.communication}</p>
                  )}
                  <p>{t.feedback}</p>
                  {t.critic_note && <p className="text-xs text-muted-foreground">Score reviewed: {t.critic_note}</p>}
                </div>
              ))}
            </div>
          </details>
        )}
        {view.done && (
          <Button asChild variant="outline"><Link to="/start">Start another session</Link></Button>
        )}
      </CardContent>
    </Card>
  );
}

function applyTick(done: Record<string, number[]>, skill: string, index: number, on: boolean) {
  const cur = new Set(done[skill] ?? []);
  if (on) cur.add(index);
  else cur.delete(index);
  return { ...done, [skill]: [...cur].sort((a, b) => a - b) };
}

/** Shown on the assessments tab while the pending skill's topics aren't all ticked. */
function AssessmentGate({ pending, current, progress, onAssess, onStudy, onTakeAnyway, onSkipAll, forced, quiz }: {
  pending: string[];
  current: string;
  progress: (skill: string) => [number, number];
  onAssess: (skill: string) => void;
  onStudy: () => void;
  onTakeAnyway: () => void;
  onSkipAll: () => void;
  forced: boolean;
  quiz: React.ReactNode;
}) {
  if (forced) return <>{quiz}</>;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Finish your topics first</CardTitle>
        <CardDescription>
          Each skill's assessment unlocks once you've ticked all of its topics on the Skill Gap & Topics tab.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {pending.map((sk) => {
          const [done, total] = progress(sk);
          const ready = total > 0 && done >= total;
          return (
            <div key={sk} className="flex flex-wrap items-center gap-3 rounded-lg border p-3">
              <div className="flex-1 min-w-[10rem]">
                <p className="text-sm font-medium">{sk}</p>
                <p className="text-xs text-muted-foreground tabular-nums">{done}/{total} topics ticked</p>
              </div>
              {ready ? (
                <Button size="sm" onClick={() => onAssess(sk)}>Take assessment</Button>
              ) : (
                <Button size="sm" variant="outline" onClick={onStudy}>Study topics</Button>
              )}
            </div>
          );
        })}
        <div className="flex flex-wrap justify-end gap-2 pt-2">
          <Button variant="ghost" size="sm" onClick={onSkipAll}>Skip to final interview</Button>
          <Button variant="ghost" size="sm" onClick={onTakeAnyway}>Take {current} assessment anyway</Button>
        </div>
      </CardContent>
    </Card>
  );
}
