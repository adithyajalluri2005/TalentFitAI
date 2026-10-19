import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { CheckCircle2, Loader2, RotateCcw, Trophy, TrendingUp, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Label } from '@/components/ui/label';
import { useToast } from '@/hooks/use-toast';
import {
  coachApi, errorMessage, CheckpointPrompt, CheckpointResult, RespondPayload, SessionView,
} from '@/services/coach';
import { CodeText, ReadinessRing, SkillRow, SourceLink } from './components';
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
  // 'study' (no quiz requested yet) lives on the plan tab.
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
      // A finished session shows its recap on the plan tab; otherwise follow
      // the graph to wherever it is now waiting.
      // After a submitted quiz, stay on the Assessments tab so its results show.
      const graded = !!payload.answers && next.waiting_for?.type === 'study';
      // The last interview answer opens the results on the interview tab.
      const interviewEnded = (payload.answer !== undefined || (tab === 'interview' && (payload.action === 'skip' || payload.action === 'end')))
        && next.state.history.length > before;
      const target = graded ? 'checkpoints' : interviewEnded ? 'interview' : tabFor(next);
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
  // One interview per session; after it, assessments stay open until the session is ended.
  const interviewDone = state.status === 'ready' || state.status === 'finished';
  const showRecap = !!lastSnapshot && (view.done || interviewDone);
  const finish = () => respond({ action: 'finish' });
  const goTo = (t: Tab) => navigate(`/session/${threadId}/${t}`);
  const topicsFor = (skill: string) => state.plan.find((p) => p.skill === skill)?.topics.length ?? 0;
  // Open this skill's assessment. Quizzes are only written on request, so this
  // asks for one (or switches from another skill's open quiz).
  const assess = (skill: string) => {
    // Go to the Assessments tab first so its "preparing" state shows while the quiz is written.
    goTo('checkpoints');
    if (waiting?.type === 'study') respond({ action: 'assess', skill });
    else if (waiting?.type === 'checkpoint' && waiting.skill !== skill) respond({ action: 'switch', skill });
  };
  // Take an already-assessed skill's assessment again; the new score replaces the old one.
  const retake = (skill: string) => {
    goTo('checkpoints');
    if (waiting?.type === 'study') respond({ action: 'retake', skill });
  };
  // Every assessment is done: write the first interview question and open the interview.
  const startInterview = () => {
    goTo('interview');
    if (waiting?.type === 'study') respond({ action: 'interview' });
  };

  const preparing = (
    <Card><CardContent className="py-16 flex flex-col items-center gap-3 text-muted-foreground">
      <Loader2 className="h-8 w-8 animate-spin text-primary" />
      <span>Preparing your assessment…</span>
      <span className="text-xs">This takes a few seconds, up to half a minute for a skill's first assessment.</span>
    </CardContent></Card>
  );
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
            <Badge variant="secondary" className="font-normal">{statusLabel(view)}</Badge>
          </div>
        </div>

        {tab === 'plan' && (
          <>
            {showRecap && <SessionRecap view={view} onRetake={view.done ? undefined : () => goTo('checkpoints')} onFinish={view.done ? undefined : finish} />}
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
                onRetake={view.done ? undefined : retake}
                onInterview={waiting?.type === 'interview_question' ? () => goTo('interview') : startInterview}
                interviewDone={interviewDone}
                onViewResults={() => goTo('interview')}
                onFinish={view.done ? undefined : finish}
              />
            )}
          </>
        )}

        {tab === 'checkpoints' && (
          busy ? preparing : waiting?.type === 'checkpoint' ? (
            <>
              <QuizPanel key={`${state.checkpoints.length}-${waiting.skill}`} prompt={waiting} onSubmit={respond} />
              {state.checkpoints.length > 0 && <LastCheckpoint result={state.checkpoints[state.checkpoints.length - 1]} />}
            </>
          ) : waiting?.type === 'study' ? (
            <>
              {/* The usual view right after submitting a quiz. */}
              {state.checkpoints.length > 0 && <LastCheckpoint result={state.checkpoints[state.checkpoints.length - 1]} defaultOpen />}
              {waiting.pending.length > 0 ? (
                <AssessmentGate
                  pending={waiting.pending}
                  progress={(sk) => [view.topic_done?.[sk]?.length ?? 0, topicsFor(sk)]}
                  onAssess={assess}
                  onStudy={() => goTo('plan')}
                  onSkipAll={interviewDone ? undefined : () => respond({ action: 'skip_all' })}
                  onFinish={interviewDone ? finish : undefined}
                />
              ) : interviewDone ? (
                <Placeholder
                  text="Your interview is done. Retake any assessment to raise your readiness, or end the session when you're finished."
                  action={{ label: 'End session', onClick: finish }}
                  secondary={{ label: 'View interview results', onClick: () => goTo('interview') }}
                />
              ) : (
                <Placeholder
                  text="All skill assessments are done. Retake any of them to improve your score, or start the final interview."
                  action={{ label: 'Start final interview', onClick: startInterview }}
                />
              )}
              <RetakeList skills={waiting.retakeable ?? []} checkpoints={state.checkpoints} onRetake={retake} />
            </>
          ) : (
            <>
              {state.checkpoints.length > 0 && <LastCheckpoint result={state.checkpoints[state.checkpoints.length - 1]} />}
              <Placeholder
                text={view.done ? 'This coaching session is complete.' : 'All skill assessments are done.'}
                action={!view.done && waiting?.type === 'interview_question' ? { label: 'Start final interview', onClick: () => goTo('interview') } : undefined}
              />
            </>
          )
        )}

        {tab === 'interview' && (
          waiting?.type === 'interview_question' ? (
            // Kept mounted while the coach thinks, so the camera stays on between questions.
            <>
              <InterviewRoom prompt={waiting} onSubmit={respond} busy={busy} />
            </>
          ) : busy ? thinking : showRecap ? (
            <SessionRecap view={view} reviewOpen onRetake={view.done ? undefined : () => goTo('checkpoints')} onFinish={view.done ? undefined : finish} />
          ) : waiting?.type === 'study' && waiting.pending.length === 0 ? (
            <Placeholder
              text="Every skill assessment is done. Start the final interview when you're ready; until then you can still retake assessments."
              action={{ label: 'Start final interview', onClick: startInterview }}
              secondary={{ label: 'Back to Skill Gap & Topics', onClick: () => goTo('plan') }}
            />
          ) : waiting?.type === 'checkpoint' || waiting?.type === 'study' ? (
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
                {Math.round(view.readiness) !== Math.round(state.history[state.history.length - 1].readiness) &&
                  ` · now ${Math.round(view.readiness)}% (live, official at session end)`}
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
  if (view.state.status === 'finished') return 'Interview done · assessments still open';
  const w = view.waiting_for;
  if (w?.type === 'checkpoint') return `Next: ${w.skill} assessment`;
  if (w?.type === 'study') return 'Study your topics, then take the assessments';
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
            <CodeText className="font-medium text-sm" text={`${i + 1}. ${q.question}`} />
            <SourceLink name={q.source_name} url={q.source_url} />
            <RadioGroup
              value={answers[i] !== undefined ? String(answers[i]) : ''}
              onValueChange={(v) => setAnswers((a) => a.map((x, j) => (j === i ? Number(v) : x)))}
            >
              {q.options.map((o, j) => (
                <div key={j} className="flex items-start gap-2">
                  <RadioGroupItem value={String(j)} id={`q${i}o${j}`} className="mt-0.5" />
                  <Label htmlFor={`q${i}o${j}`} className="font-normal text-sm leading-snug cursor-pointer"><CodeText text={o} /></Label>
                </div>
              ))}
            </RadioGroup>
          </div>
        ))}
        <div className="flex flex-wrap gap-2 justify-end pt-2">
          {!prompt.interview_done && (
            <Button variant="ghost" onClick={() => onSubmit({ action: 'skip_all' })}>Skip to final interview</Button>
          )}
          <Button variant="outline" onClick={() => onSubmit({ action: 'skip' })}>Skip this assessment</Button>
          <Button disabled={!complete} onClick={() => onSubmit({ answers: answers as number[] })}>Submit answers</Button>
        </div>
      </CardContent>
    </Card>
  );
}

function LastCheckpoint({ result, defaultOpen = false }: { result: CheckpointResult; defaultOpen?: boolean }) {
  if (result.skipped) return null;
  const pct = Math.round(result.score * 100);
  const summary = (
    <span className="inline-flex items-center gap-2">
      <CheckCircle2 className={cn('h-4 w-4', pct >= 75 ? 'text-success' : 'text-warning')} />
      Last assessment — {result.skill}: {pct}% correct. Your skill level was updated.
    </span>
  );
  if (!result.review?.length) return <p className="text-sm text-muted-foreground">{summary}</p>;
  return (
    <details open={defaultOpen} className="text-sm rounded-lg border bg-muted/40 p-4">
      <summary className="cursor-pointer text-muted-foreground">{summary} <span className="underline">Review answers</span></summary>
      <ol className="mt-4 space-y-4">
        {result.review.map((q, i) => {
          const right = q.chosen === q.answer_index;
          return (
            <li key={i} className="space-y-1">
              <div className="font-medium flex items-start gap-2">
                {right
                  ? <CheckCircle2 className="h-4 w-4 mt-0.5 shrink-0 text-success" />
                  : <XCircle className="h-4 w-4 mt-0.5 shrink-0 text-destructive" />}
                <CodeText className="min-w-0 flex-1" text={`${i + 1}. ${q.question}`} />
              </div>
              <div className="pl-6 space-y-1">
                {!right && (
                  <div className="text-muted-foreground flex gap-1">Your answer: <CodeText text={q.options[q.chosen] ?? '—'} /></div>
                )}
                <div className="flex gap-1">Correct answer: <CodeText className="font-medium" text={q.options[q.answer_index]} /></div>
                {q.explanation && <p className="text-muted-foreground">{q.explanation}</p>}
                <SourceLink name={q.source_name} url={q.source_url} label="Learn the answer" />
              </div>
            </li>
          );
        })}
      </ol>
    </details>
  );
}

function KeyPoints({ points }: { points: string[] }) {
  if (!points?.length) return null;
  return (
    <div>
      <p className="text-xs font-medium">A strong answer covers:</p>
      <ul className="list-disc list-inside text-xs text-muted-foreground space-y-0.5">
        {points.map((p, i) => <li key={i}>{p}</li>)}
      </ul>
    </div>
  );
}

// ---------------- end of session ----------------

function SessionRecap({ view, reviewOpen = false, onRetake, onFinish }: {
  view: SessionView;
  reviewOpen?: boolean;
  /** shown while the session is open: assessments can still be retaken after the interview */
  onRetake?: () => void;
  onFinish?: () => void;
}) {
  const { state } = view;
  const last = state.history[state.history.length - 1];
  const ready = state.status === 'ready';
  return (
    <Card className={cn(ready ? 'border-success' : 'border-primary/40')}>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          {ready ? <Trophy className="h-5 w-5 text-success" /> : <TrendingUp className="h-5 w-5 text-primary" />}
          {ready ? 'You are interview-ready!' : view.done ? 'Coaching complete' : 'Interview results'}
        </CardTitle>
        <CardDescription>
          Readiness {Math.round(last.readiness)}% (target {state.target_readiness}%)
          {state.history.length > 1 && ` · was ${Math.round(state.history[0].readiness)}% right after the interview`}
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
        {state.interview.length > 0 && (
          <details className="text-sm" open={reviewOpen}>
            <summary className="cursor-pointer font-medium">Interview review ({state.interview.length} question{state.interview.length === 1 ? '' : 's'})</summary>
            <div className="mt-3 space-y-3">
              {state.interview.map((t, i) => (
                <div key={i} className="space-y-1.5 rounded-lg border p-3">
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <Badge variant="secondary">Q{i + 1}</Badge>
                    <span className="text-muted-foreground">{t.skill}{t.is_follow_up ? ' · follow-up' : ''}</span>
                    {t.score && (
                      <Badge variant="outline" className={cn('ml-auto tabular-nums',
                        avgScore(t.score) >= 3.5 ? 'text-success' : avgScore(t.score) >= 2.5 ? 'text-warning' : 'text-destructive')}>
                        {avgScore(t.score).toFixed(1)} / 5
                      </Badge>
                    )}
                  </div>
                  <p className="font-medium">{t.question}</p>
                  {t.answer === 'SKIPPED' || t.answer === 'NO_ANSWER'
                    ? <p className="text-muted-foreground text-sm">{t.answer === 'SKIPPED' ? 'Skipped' : 'No answer given'}</p>
                    : <p className="text-muted-foreground italic">“{t.answer}”</p>}
                  {t.score && (
                    <p className="text-xs">Correctness {t.score.correctness} · Depth {t.score.depth} · Communication {t.score.communication}</p>
                  )}
                  <p>{t.feedback}</p>
                  {t.critic_note && <p className="text-xs text-muted-foreground">Score reviewed: {t.critic_note}</p>}
                  <KeyPoints points={t.key_points} />
                  <SourceLink name={t.source_name} url={t.source_url} label="Learn the answer" />
                </div>
              ))}
            </div>
          </details>
        )}
        <div className="flex flex-wrap gap-2">
          {onRetake && (
            <Button onClick={onRetake}><RotateCcw className="h-4 w-4 mr-1.5" /> Retake assessments to improve</Button>
          )}
          {onFinish && <Button variant="outline" onClick={onFinish}>End session</Button>}
          <Button asChild variant="outline"><Link to="/start">Start another session</Link></Button>
        </div>
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
function AssessmentGate({ pending, progress, onAssess, onStudy, onSkipAll, onFinish }: {
  pending: string[];
  progress: (skill: string) => [number, number];
  onAssess: (skill: string) => void;
  onStudy: () => void;
  /** omitted after the interview */
  onSkipAll?: () => void;
  /** after the interview: end the session without the pending assessments */
  onFinish?: () => void;
}) {
  const current = pending[0];
  const [currentDone, currentTotal] = current ? progress(current) : [0, 0];
  // Once its topics are all ticked, the skill's own "Take assessment" button covers it.
  const currentReady = currentTotal > 0 && currentDone >= currentTotal;
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
          {onSkipAll && <Button variant="ghost" size="sm" onClick={onSkipAll}>Skip to final interview</Button>}
          {onFinish && <Button variant="ghost" size="sm" onClick={onFinish}>End session</Button>}
          {!currentReady && (
            <Button variant="ghost" size="sm" onClick={() => onAssess(current)}>Take {current} assessment anyway</Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

/** Assessments already taken, each with its latest score and a retake button. */
function RetakeList({ skills, checkpoints, onRetake }: {
  skills: string[];
  checkpoints: CheckpointResult[];
  onRetake: (skill: string) => void;
}) {
  if (!skills.length) return null;
  const latest = new Map(checkpoints.map((c) => [c.skill, c] as const));
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Retake an assessment</CardTitle>
        <CardDescription>You get new questions, and your latest score replaces the earlier one.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {skills.map((sk) => {
          const r = latest.get(sk);
          return (
            <div key={sk} className="flex flex-wrap items-center gap-3 rounded-lg border p-3">
              <div className="flex-1 min-w-[10rem]">
                <p className="text-sm font-medium">{sk}</p>
                <p className="text-xs text-muted-foreground tabular-nums">
                  {r?.skipped ? 'Skipped' : r ? `Last score ${Math.round(r.score * 100)}%` : ''}
                </p>
              </div>
              <Button size="sm" variant="outline" onClick={() => onRetake(sk)}>
                <RotateCcw className="h-3.5 w-3.5 mr-1.5" /> {r?.skipped ? 'Take assessment' : 'Retake'}
              </Button>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

function avgScore(s: { correctness: number; depth: number; communication: number }) {
  return (s.correctness + s.depth + s.communication) / 3;
}
