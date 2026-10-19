import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowDownRight, ArrowRight, ArrowUpRight, BookOpen, Check, ChevronDown, ClipboardCheck, FileText, Gauge,
  Loader2, MessageSquare, PartyPopper, Plus, Sparkles, Target, Trophy, TrendingUp,
} from 'lucide-react';
import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress as ProgressBar } from '@/components/ui/progress';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { cn } from '@/lib/utils';
import { coachApi, errorMessage, getCandidateId, ProgressRow, savedSessions, SessionView, SkillLevel } from '@/services/coach';
import { ReadinessRing } from './components';

const DEFAULT_TARGET = 90;
/** An assessment at or above this score counts as passed. */
const PASS_SCORE = 0.75;

export default function Progress() {
  const [rows, setRows] = useState<ProgressRow[] | null>(null);
  const [views, setViews] = useState<SessionView[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [role, setRole] = useState<string>('');

  useEffect(() => {
    coachApi.progress(getCandidateId())
      .then(setRows)
      .catch((e) => setError(errorMessage(e)));
    Promise.all(savedSessions().slice(0, 3).map((s) => coachApi.session(s.threadId).catch(() => null)))
      .then((vs) => setViews(vs.filter((v): v is SessionView => !!v)));
  }, []);

  const primary = views?.[0] ?? null;

  useEffect(() => {
    if (role || !rows) return;
    setRole(primary?.state.target_role ?? rows[rows.length - 1]?.target_role ?? '');
  }, [rows, primary, role]);

  const roles = useMemo(() => [...new Set((rows ?? []).map((r) => r.target_role))], [rows]);
  const series = useMemo(() => (rows ?? []).filter((r) => r.target_role === role), [rows, role]);

  if (error) return <p className="text-destructive text-center py-24">{error}</p>;
  if (!rows || !views) return <div className="py-24 flex justify-center"><Loader2 className="h-8 w-8 animate-spin text-primary" /></div>;
  if (!rows.length && !views.length) return <Welcome />;

  // Live session for the chosen role: the chart extends to its live estimate.
  const roleView = views.find((v) => v.state.target_role === role) ?? null;
  const target = primary?.state.target_readiness ?? DEFAULT_TARGET;

  return (
    <div className="max-w-5xl mx-auto space-y-6 pb-12">
      <DashboardHeader />
      {primary ? <Hero view={primary} lastOfficial={lastOfficial(rows, primary)} /> : <HeroNoSession rows={rows} />}
      {primary && <Journey view={primary} />}
      {primary && <Stats view={primary} lastOfficial={lastOfficial(rows, primary)} />}
      {primary && <SkillGrid view={primary} />}
      {views.length > 1 && <OtherSessions views={views.slice(1)} />}

      <div className="flex flex-wrap items-end justify-between gap-4 pt-2">
        <div>
          <h2 className="text-lg font-semibold">Readiness over time</h2>
          <p className="text-muted-foreground text-sm">Official re-scores at the end of each coaching session, plus where you are now.</p>
        </div>
        {roles.length > 1 && (
          <Select value={role} onValueChange={setRole}>
            <SelectTrigger className="w-64"><SelectValue /></SelectTrigger>
            <SelectContent>{roles.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
          </Select>
        )}
      </div>
      <ReadinessChart role={role} series={series} live={roleView?.readiness ?? null} target={roleView?.state.target_readiness ?? target} />
      {series.length > 0 && <HistoryTable series={series} />}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* helpers                                                             */
/* ------------------------------------------------------------------ */

function lastOfficial(rows: ProgressRow[], v: SessionView): number | null {
  const own = rows.filter((r) => r.thread_id === v.thread_id);
  if (own.length) return own[own.length - 1].readiness;
  const h = v.state.history;
  return h.length ? h[h.length - 1].readiness : null;
}

function topicCounts(v: SessionView) {
  const total = v.state.plan.reduce((n, s) => n + s.topics.length, 0);
  const done = Object.values(v.topic_done ?? {}).reduce((n, ix) => n + ix.length, 0);
  return { done: Math.min(done, total), total };
}

function topicsComplete(v: SessionView, skill: string) {
  const plan = v.state.plan.find((p) => p.skill === skill);
  if (!plan || !plan.topics.length) return true;
  return (v.topic_done?.[skill]?.length ?? 0) >= plan.topics.length;
}

/** Latest non-skipped score per skill. */
function latestScores(v: SessionView): Record<string, number> {
  const out: Record<string, number> = {};
  for (const c of v.state.checkpoints) if (!c.skipped) out[c.skill] = c.score;
  return out;
}

function interviewDone(v: SessionView) {
  return v.state.status === 'ready' || v.state.status === 'finished' || !!(v.waiting_for && 'interview_done' in v.waiting_for && v.waiting_for.interview_done);
}

interface NextAction { label: string; hint: string; to: string; icon: typeof ArrowRight }

function nextAction(v: SessionView): NextAction {
  const base = `/session/${v.thread_id}`;
  const w = v.waiting_for;
  if (v.done) return { label: 'View your results', hint: 'This coaching session is complete.', to: `${base}/plan`, icon: Trophy };
  if (w?.type === 'checkpoint') return { label: `Take ${w.skill} assessment`, hint: 'Your assessment is ready and waiting.', to: `${base}/checkpoints`, icon: ClipboardCheck };
  if (w?.type === 'interview_question') return { label: 'Continue mock interview', hint: `Question ${w.turn} of ${w.of} is waiting.`, to: `${base}/interview`, icon: MessageSquare };
  if (w?.type === 'study') {
    const ready = w.pending.find((s) => topicsComplete(v, s));
    if (ready) return { label: `Take ${ready} assessment`, hint: `You've studied every ${ready} topic.`, to: `${base}/checkpoints`, icon: ClipboardCheck };
    if (w.pending.length) return { label: `Study ${w.pending[0]}`, hint: 'Your biggest gap right now.', to: `${base}/plan`, icon: BookOpen };
    if (!w.interview_done) return { label: 'Start final interview', hint: 'All assessments done.', to: `${base}/interview`, icon: MessageSquare };
    // After the interview: retaking the weakest skill's assessment is what raises readiness.
    const weakest = [...v.state.skills]
      .filter((s) => s.level < s.required_level && w.retakeable.includes(s.skill))
      .sort((a, b) => b.jd_weight * (b.required_level - b.level) - a.jd_weight * (a.required_level - a.level))[0];
    if (weakest) return { label: `Retake ${weakest.skill} assessment`, hint: 'Your biggest gap. A better score raises your readiness.', to: `${base}/checkpoints`, icon: ClipboardCheck };
    return { label: 'View interview results', hint: 'Your interview is done.', to: `${base}/interview`, icon: Trophy };
  }
  return { label: 'Continue', hint: 'Pick up where you left off.', to: `${base}/plan`, icon: ArrowRight };
}

/* ------------------------------------------------------------------ */
/* sections                                                            */
/* ------------------------------------------------------------------ */

function DashboardHeader() {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="text-muted-foreground text-sm">Pick up where you left off and track your readiness.</p>
      </div>
      <Button asChild variant="outline">
        <Link to="/start"><Plus className="h-4 w-4 mr-1" /> New session</Link>
      </Button>
    </div>
  );
}

function Hero({ view, lastOfficial }: { view: SessionView; lastOfficial: number | null }) {
  const target = view.state.target_readiness;
  const live = view.readiness;
  const reached = live >= target;
  const action = nextAction(view);
  const Icon = action.icon;
  const delta = lastOfficial == null ? null : Math.round(live - lastOfficial);
  const done = interviewDone(view);

  return (
    <div className="space-y-4">
      {reached && (
        <div className="flex flex-col sm:flex-row sm:items-center gap-3 rounded-xl border border-success/40 bg-success/10 px-5 py-4">
          <PartyPopper className="h-6 w-6 text-success shrink-0" />
          <div className="flex-1">
            <p className="font-semibold">You're interview-ready for {view.state.target_role}!</p>
            <p className="text-sm text-muted-foreground">
              {done ? 'You hit your target. Retake assessments any time to keep sharpening.' : `You've reached the ${target}% target. Prove it in the final mock interview.`}
            </p>
          </div>
          {!done && !view.done && (
            <Button asChild className="bg-success text-success-foreground hover:bg-success/90 shrink-0">
              <Link to={`/session/${view.thread_id}/interview`}>Start final interview <ArrowRight className="h-4 w-4 ml-1" /></Link>
            </Button>
          )}
        </div>
      )}

      <Card className="overflow-hidden border-0 shadow-md bg-gradient-to-br from-primary/15 via-card to-success/10">
        <CardContent className="p-6 sm:p-8 flex flex-col md:flex-row items-center gap-8">
          <div className="relative shrink-0">
            <ReadinessRing value={live} target={target} size={168} />
          </div>
          <div className="flex-1 space-y-4 text-center md:text-left">
            <div className="space-y-1">
              <p className="text-sm font-medium text-primary flex items-center gap-1 justify-center md:justify-start">
                <Sparkles className="h-4 w-4" /> Welcome back
              </p>
              <h2 className="text-2xl sm:text-3xl font-bold leading-tight">
                You're {Math.round(live)}% interview-ready
              </h2>
              <p className="text-muted-foreground">
                for <span className="font-medium text-foreground">{view.state.target_role}</span>
                {delta != null && delta !== 0 && (
                  <> · <span className={delta > 0 ? 'text-success font-medium' : 'text-destructive font-medium'}>
                    {delta > 0 ? '+' : ''}{delta} pts</span> since your last re-score</>
                )}
              </p>
            </div>
            <div className="flex flex-col sm:flex-row items-center gap-3 md:justify-start justify-center">
              <Button asChild size="lg" className="shadow-sm">
                <Link to={action.to}><Icon className="h-4 w-4 mr-2" /> {action.label} <ArrowRight className="h-4 w-4 ml-2" /></Link>
              </Button>
              <span className="text-sm text-muted-foreground">{action.hint}</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function HeroNoSession({ rows }: { rows: ProgressRow[] }) {
  const latest = rows[rows.length - 1];
  return (
    <Card className="overflow-hidden border-0 shadow-md bg-gradient-to-br from-primary/15 via-card to-success/10">
      <CardContent className="p-6 sm:p-8 flex flex-col md:flex-row items-center gap-8">
        <div className="relative shrink-0">
          <ReadinessRing value={latest.readiness} target={DEFAULT_TARGET} size={168} />
        </div>
        <div className="flex-1 space-y-3 text-center md:text-left">
          <h2 className="text-2xl font-bold">Last scored {Math.round(latest.readiness)}% for {latest.target_role}</h2>
          <p className="text-muted-foreground">Start a new session to keep closing your skill gaps.</p>
          <Button asChild size="lg"><Link to="/start">Start a session <ArrowRight className="h-4 w-4 ml-2" /></Link></Button>
        </div>
      </CardContent>
    </Card>
  );
}

const STEPS = [
  { label: 'Resume & Role', icon: FileText },
  { label: 'Skill Gap & Topics', icon: BookOpen },
  { label: 'Assessments', icon: ClipboardCheck },
  { label: 'Final Interview', icon: MessageSquare },
  { label: 'Interview-ready', icon: Trophy },
];

function Journey({ view }: { view: SessionView }) {
  const t = topicCounts(view);
  const w = view.waiting_for;
  const pending = w && 'pending' in w ? w.pending.length : 0;
  const idone = interviewDone(view);
  const done = [
    true,
    view.state.checkpoints.length > 0 || (t.total > 0 && t.done >= t.total),
    idone || (w?.type === 'study' && pending === 0) || w?.type === 'interview_question',
    idone,
    view.state.status === 'ready',
  ];
  const current = done.findIndex((d) => !d);

  return (
    <Card>
      <CardContent className="py-5 px-4 sm:px-6">
        <ol className="flex items-start">
          {STEPS.map((s, i) => {
            const isDone = done[i];
            const isCurrent = i === current;
            const Icon = s.icon;
            return (
              <li key={s.label} className="flex-1 flex flex-col items-center relative">
                {i > 0 && (
                  <span className={cn('absolute top-4 right-1/2 w-full h-0.5 -z-0', done[i - 1] ? 'bg-success' : 'bg-border')} />
                )}
                <span className={cn(
                  'relative z-10 h-8 w-8 rounded-full flex items-center justify-center border-2 transition-colors',
                  isDone ? 'bg-success border-success text-success-foreground'
                    : isCurrent ? 'bg-primary border-primary text-primary-foreground ring-4 ring-primary/20'
                    : 'bg-card border-border text-muted-foreground',
                )}>
                  {isDone ? <Check className="h-4 w-4" /> : <Icon className="h-4 w-4" />}
                </span>
                <span className={cn('mt-2 text-[11px] sm:text-xs text-center leading-tight px-1',
                  isCurrent ? 'font-semibold text-foreground' : 'text-muted-foreground')}>
                  {s.label}
                </span>
              </li>
            );
          })}
        </ol>
      </CardContent>
    </Card>
  );
}

function Stats({ view, lastOfficial }: { view: SessionView; lastOfficial: number | null }) {
  const t = topicCounts(view);
  const scores = latestScores(view);
  const assessed = view.state.plan.map((p) => p.skill);
  const passed = assessed.filter((s) => (scores[s] ?? 0) >= PASS_SCORE).length;
  const gaps = view.state.skills.filter((s) => s.level < s.required_level).length;
  const delta = lastOfficial == null ? null : view.readiness - lastOfficial;

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <Stat icon={Gauge} tone="primary" label="Readiness (live)" value={`${Math.round(view.readiness)}%`}
            trend={delta == null ? undefined : delta} trendLabel="vs last re-score" />
      <Stat icon={BookOpen} tone="primary" label="Topics studied" value={`${t.done}/${t.total}`}
            bar={t.total ? (100 * t.done) / t.total : 0} />
      <Stat icon={ClipboardCheck} tone="success" label="Assessments passed" value={`${passed}/${assessed.length}`}
            bar={assessed.length ? (100 * passed) / assessed.length : 0} />
      <Stat icon={Target} tone={gaps ? 'warning' : 'success'} label="Skill gaps left" value={String(gaps)}
            sub={`of ${view.state.skills.length} role skills`} />
    </div>
  );
}

const TONES = {
  primary: 'bg-primary/10 text-primary',
  success: 'bg-success/15 text-success',
  warning: 'bg-warning/15 text-warning',
};

function Stat({ icon: Icon, tone, label, value, trend, trendLabel, bar, sub }: {
  icon: typeof Gauge; tone: keyof typeof TONES; label: string; value: string;
  trend?: number; trendLabel?: string; bar?: number; sub?: string;
}) {
  return (
    <Card>
      <CardContent className="pt-5 space-y-2">
        <div className="flex items-center gap-2">
          <span className={cn('h-8 w-8 rounded-lg flex items-center justify-center', TONES[tone])}><Icon className="h-4 w-4" /></span>
          <p className="text-xs text-muted-foreground leading-tight">{label}</p>
        </div>
        <p className="text-2xl font-bold tabular-nums">{value}</p>
        {trend != null && (
          <p className={cn('text-xs flex items-center gap-0.5', trend > 0 ? 'text-success' : trend < 0 ? 'text-destructive' : 'text-muted-foreground')}>
            {trend > 0 ? <ArrowUpRight className="h-3 w-3" /> : trend < 0 ? <ArrowDownRight className="h-3 w-3" /> : null}
            {trend > 0 ? '+' : ''}{Math.round(trend)} pts <span className="text-muted-foreground ml-1">{trendLabel}</span>
          </p>
        )}
        {bar != null && <ProgressBar value={bar} className="h-1.5" />}
        {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
      </CardContent>
    </Card>
  );
}

function skillStatus(s: SkillLevel) {
  const gap = s.required_level - s.level;
  if (gap <= 0) return { label: 'Strong', badge: 'bg-success/15 text-success border-success/30', bar: 'bg-success' };
  if (gap <= 1) return { label: 'Close', badge: 'bg-primary/10 text-primary border-primary/30', bar: 'bg-primary' };
  return { label: 'Gap', badge: 'bg-warning/15 text-warning border-warning/40', bar: 'bg-warning' };
}

function SkillGrid({ view }: { view: SessionView }) {
  const base = `/session/${view.thread_id}`;
  const w = view.waiting_for;
  const pending = new Set(w && 'pending' in w ? w.pending : []);
  const retakeable = new Set(w?.type === 'study' ? w.retakeable : []);
  const skills = [...view.state.skills].sort(
    (a, b) => b.jd_weight * (b.required_level - b.level) - a.jd_weight * (a.required_level - a.level),
  );

  return (
    <div className="space-y-3">
      <div className="flex items-end justify-between">
        <div>
          <h2 className="text-lg font-semibold">Your skills</h2>
          <p className="text-muted-foreground text-sm">Biggest gaps first. The line marks what the role needs.</p>
        </div>
      </div>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {skills.map((s) => {
          const st = skillStatus(s);
          const inPlan = view.state.plan.some((p) => p.skill === s.skill);
          const canAssess = (pending.has(s.skill) || retakeable.has(s.skill)) && topicsComplete(view, s.skill);
          const assessLabel = retakeable.has(s.skill) ? 'Retake assessment' : 'Take assessment';
          return (
            <Card key={s.skill} className="flex flex-col">
              <CardContent className="pt-5 flex-1 flex flex-col gap-3">
                <div className="flex items-start justify-between gap-2">
                  <p className="font-medium leading-tight">{s.skill}</p>
                  <Badge variant="outline" className={cn('shrink-0 font-medium', st.badge)}>{st.label}</Badge>
                </div>
                <div className="space-y-1">
                  <div className="relative h-2 rounded-full bg-muted overflow-visible">
                    <div className={cn('h-2 rounded-full transition-all', st.bar)} style={{ width: `${Math.min(100, (s.level / 5) * 100)}%` }} />
                    <span className="absolute -top-1 h-4 w-0.5 bg-foreground rounded" style={{ left: `${(s.required_level / 5) * 100}%` }} />
                  </div>
                  <p className="text-xs text-muted-foreground tabular-nums">Level {s.level.toFixed(1)} · needs {s.required_level}</p>
                </div>
                {st.label !== 'Strong' && inPlan && (
                  <Button asChild variant={canAssess ? 'default' : 'secondary'} size="sm" className="mt-auto w-full">
                    <Link to={`${base}/${canAssess ? 'checkpoints' : 'plan'}`}>
                      {canAssess ? <><ClipboardCheck className="h-4 w-4 mr-1" /> {assessLabel}</> : <><BookOpen className="h-4 w-4 mr-1" /> Study topics</>}
                    </Link>
                  </Button>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

function OtherSessions({ views }: { views: SessionView[] }) {
  return (
    <Card>
      <CardHeader className="pb-3"><CardTitle className="text-base">Other coaching sessions</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        {views.map((v) => {
          const a = nextAction(v);
          return (
            <div key={v.thread_id} className="flex flex-col sm:flex-row sm:items-center gap-3 rounded-lg border p-4">
              <div className="flex-1 min-w-0 space-y-2">
                <span className="font-semibold">{v.state.target_role}</span>
                <div className="flex items-center gap-3">
                  <ProgressBar value={v.readiness} className="h-2 flex-1" />
                  <span className="text-sm font-semibold tabular-nums w-12 text-right">{Math.round(v.readiness)}%</span>
                </div>
              </div>
              <Button asChild variant="outline" className="shrink-0">
                <Link to={a.to}>{a.label} <ArrowRight className="h-4 w-4 ml-1" /></Link>
              </Button>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

function ReadinessChart({ role, series, live, target }: { role: string; series: ProgressRow[]; live: number | null; target: number }) {
  const data = useMemo(() => {
    const pts: { label: string; date: string; readiness?: number; live?: number }[] = series.map((r, i) => ({
      label: `#${i + 1}`,
      date: new Date(r.created_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }),
      readiness: r.readiness,
    }));
    const last = pts[pts.length - 1];
    if (live != null && (!last || Math.round(live) !== Math.round(last.readiness ?? -1))) {
      if (last) last.live = last.readiness;
      pts.push({ label: 'Now', date: 'Live estimate', live });
    }
    return pts;
  }, [series, live]);

  if (!data.length) {
    return (
      <Card>
        <CardContent className="py-10 text-center space-y-2">
          <TrendingUp className="h-8 w-8 text-muted-foreground mx-auto" />
          <p className="font-medium">Your progress chart appears after your first re-score</p>
          <p className="text-sm text-muted-foreground">Each completed coaching session re-scores your readiness and adds a point here.</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{role}</CardTitle>
        <CardDescription>
          Solid: official re-scores · dotted: live estimate · dashed line: {target}% interview-ready target.
          {series.length < 2 && ' Complete more sessions to see your trend.'}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data} margin={{ top: 16, right: 16, bottom: 0, left: -12 }}>
              <defs>
                <linearGradient id="readinessFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} stroke="hsl(var(--border))" />
              <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 12 }} />
              <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tickLine={false} axisLine={false}
                     tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 12 }} tickFormatter={(v) => `${v}%`} />
              <ReferenceLine y={target} stroke="hsl(var(--success))" strokeDasharray="4 4"
                             label={{ value: `Target ${target}%`, position: 'insideBottomRight', fill: 'hsl(var(--success))', fontSize: 11 }} />
              <Tooltip
                cursor={{ stroke: 'hsl(var(--border))' }}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const p = payload[0].payload as (typeof data)[number];
                  const v = p.readiness ?? p.live ?? 0;
                  return (
                    <div className="rounded-md border bg-popover px-3 py-2 text-xs shadow-md">
                      <p className="font-medium text-foreground">{Math.round(v)}% ready</p>
                      <p className="text-muted-foreground">{p.date}</p>
                    </div>
                  );
                }}
              />
              <Line type="monotone" dataKey="live" stroke="hsl(var(--primary))" strokeWidth={2} strokeDasharray="5 5"
                    dot={{ r: 5, strokeWidth: 2, stroke: 'hsl(var(--primary))', fill: 'hsl(var(--card))' }}
                    isAnimationActive={false} connectNulls />
              <Area type="monotone" dataKey="readiness" stroke="hsl(var(--primary))" strokeWidth={2.5} fill="url(#readinessFill)"
                    dot={{ r: 4, strokeWidth: 2, stroke: 'hsl(var(--card))', fill: 'hsl(var(--primary))' }}
                    activeDot={{ r: 6, strokeWidth: 2, stroke: 'hsl(var(--card))' }} isAnimationActive={false} connectNulls={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

function HistoryTable({ series }: { series: ProgressRow[] }) {
  const latest = series[series.length - 1];
  return (
    <details className="group rounded-lg border bg-card">
      <summary className="cursor-pointer list-none flex items-center justify-between px-6 py-4 text-sm font-medium">
        History detail: skill levels by re-score
        <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform group-open:rotate-180" />
      </summary>
      <div className="px-6 pb-4 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-muted-foreground border-b">
              <th className="py-2 pr-4 font-medium">Skill</th>
              {series.map((_, i) => <th key={i} className="py-2 px-2 font-medium text-right tabular-nums">#{i + 1}</th>)}
            </tr>
          </thead>
          <tbody>
            {Object.keys(latest.per_skill).map((skill) => (
              <tr key={skill} className="border-b last:border-0">
                <td className="py-2 pr-4">{skill}</td>
                {series.map((s, i) => (
                  <td key={i} className="py-2 px-2 text-right tabular-nums">{s.per_skill[skill]?.toFixed(1) ?? '—'}</td>
                ))}
              </tr>
            ))}
            <tr className="font-medium">
              <td className="py-2 pr-4">Readiness</td>
              {series.map((s, i) => <td key={i} className="py-2 px-2 text-right tabular-nums">{Math.round(s.readiness)}%</td>)}
            </tr>
          </tbody>
        </table>
      </div>
    </details>
  );
}

/* ------------------------------------------------------------------ */
/* first visit                                                         */
/* ------------------------------------------------------------------ */

const HOW = [
  { icon: FileText, title: 'Upload your resume', text: 'Pick a target role. We rate every skill the job needs against your experience.' },
  { icon: BookOpen, title: 'Close your skill gaps', text: 'Study curated topics and videos, then prove it with short assessments.' },
  { icon: MessageSquare, title: 'Ace the mock interview', text: 'An adaptive camera interview re-scores your readiness for the real thing.' },
];

function Welcome() {
  return (
    <div className="max-w-5xl mx-auto space-y-10 pb-12">
      <Card className="overflow-hidden border-0 shadow-md bg-gradient-to-br from-primary/15 via-card to-success/10">
        <CardContent className="p-8 sm:p-12 flex flex-col md:flex-row items-center gap-10">
          <div className="flex-1 space-y-5 text-center md:text-left">
            <Badge variant="secondary" className="gap-1"><Sparkles className="h-3 w-3" /> AI career coach</Badge>
            <h1 className="text-3xl sm:text-4xl font-bold leading-tight">
              Know exactly how ready you are for your next role
            </h1>
            <p className="text-muted-foreground text-lg">
              TalentFit AI finds your skill gaps, builds a study plan, and coaches you through a mock interview
              until you're interview-ready.
            </p>
            <Button asChild size="lg" className="shadow-sm">
              <Link to="/start">Start coaching, it's free <ArrowRight className="h-4 w-4 ml-2" /></Link>
            </Button>
          </div>
          <div className="relative shrink-0 rounded-2xl bg-card/80 border shadow-sm p-6 flex flex-col items-center gap-2">
            <div className="relative">
              <ReadinessRing value={68} target={DEFAULT_TARGET} size={168} />
            </div>
            <p className="text-xs text-muted-foreground">Example readiness score</p>
          </div>
        </CardContent>
      </Card>

      <div className="space-y-4">
        <h2 className="text-xl font-semibold text-center">How it works</h2>
        <div className="grid md:grid-cols-3 gap-4">
          {HOW.map((h, i) => (
            <Card key={h.title}>
              <CardContent className="pt-6 space-y-3">
                <div className="flex items-center gap-3">
                  <span className="h-10 w-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center"><h.icon className="h-5 w-5" /></span>
                  <span className="text-sm font-semibold text-muted-foreground">Step {i + 1}</span>
                </div>
                <p className="font-semibold">{h.title}</p>
                <p className="text-sm text-muted-foreground">{h.text}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
