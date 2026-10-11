import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Loader2, Plus, TrendingUp } from 'lucide-react';
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress as ProgressBar } from '@/components/ui/progress';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { coachApi, errorMessage, getCandidateId, ProgressRow, savedSessions, SessionView } from '@/services/coach';

const TARGET = 75;

export default function Progress() {
  const [rows, setRows] = useState<ProgressRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [role, setRole] = useState<string>('');

  useEffect(() => {
    coachApi.progress(getCandidateId())
      .then((r) => {
        setRows(r);
        if (r.length) setRole(r[r.length - 1].target_role);
      })
      .catch((e) => setError(errorMessage(e)));
  }, []);

  const roles = useMemo(() => [...new Set((rows ?? []).map((r) => r.target_role))], [rows]);
  const series = useMemo(
    () => (rows ?? []).filter((r) => r.target_role === role).map((r, i) => ({
      ...r,
      label: `#${i + 1}`,
      date: new Date(r.created_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }),
    })),
    [rows, role],
  );
  const latest = series[series.length - 1];
  const first = series[0];

  if (error) return <p className="text-destructive text-center py-24">{error}</p>;
  if (!rows) return <div className="py-24 flex justify-center"><Loader2 className="h-8 w-8 animate-spin text-primary" /></div>;

  if (!rows.length) {
    if (!savedSessions().length) {
      return (
        <div className="max-w-md mx-auto py-24 text-center space-y-4">
          <TrendingUp className="h-10 w-10 text-muted-foreground mx-auto" />
          <h1 className="text-xl font-semibold">Welcome to your career coach</h1>
          <p className="text-muted-foreground">Upload your resume, pick a target role, and your readiness will be tracked here after every mock interview.</p>
          <Button asChild><Link to="/start">Start coaching</Link></Button>
        </div>
      );
    }
    return (
      <div className="max-w-4xl mx-auto space-y-6 pb-12">
        <DashboardHeader />
        <ActiveSessions />
        <Card>
          <CardContent className="py-10 text-center space-y-2">
            <TrendingUp className="h-8 w-8 text-muted-foreground mx-auto" />
            <p className="font-medium">Your progress chart appears after your first mock interview</p>
            <p className="text-sm text-muted-foreground">Each completed interview re-scores your readiness and adds a point here.</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6 pb-12">
      <DashboardHeader />
      <ActiveSessions />
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">Readiness over time</h2>
          <p className="text-muted-foreground text-sm">Re-scored after every coaching cycle.</p>
        </div>
        {roles.length > 1 && (
          <Select value={role} onValueChange={setRole}>
            <SelectTrigger className="w-64"><SelectValue /></SelectTrigger>
            <SelectContent>{roles.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
          </Select>
        )}
      </div>

      <div className="grid sm:grid-cols-3 gap-4">
        <Stat label="Current readiness" value={`${Math.round(latest.readiness)}%`} />
        <Stat label="Change since first re-score" value={`${latest.readiness - first.readiness >= 0 ? '+' : ''}${Math.round(latest.readiness - first.readiness)} pts`} />
        <Stat label="Coaching cycles" value={String(series.length)} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{role} — readiness over time</CardTitle>
          <CardDescription>Dashed line marks the {TARGET}% interview-ready target.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={series} margin={{ top: 8, right: 16, bottom: 0, left: -12 }}>
                <CartesianGrid vertical={false} stroke="hsl(var(--border))" />
                <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 12 }} />
                <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tickLine={false} axisLine={false}
                       tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 12 }} tickFormatter={(v) => `${v}%`} />
                <ReferenceLine y={TARGET} stroke="hsl(var(--muted-foreground))" strokeDasharray="4 4" />
                <Tooltip
                  cursor={{ stroke: 'hsl(var(--border))' }}
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const p = payload[0].payload as (typeof series)[number];
                    return (
                      <div className="rounded-md border bg-popover px-3 py-2 text-xs shadow-md">
                        <p className="font-medium text-foreground">{Math.round(p.readiness)}% ready</p>
                        <p className="text-muted-foreground">{p.date}</p>
                      </div>
                    );
                  }}
                />
                <Line type="monotone" dataKey="readiness" stroke="hsl(var(--primary))" strokeWidth={2}
                      dot={{ r: 4, strokeWidth: 2, stroke: 'hsl(var(--card))', fill: 'hsl(var(--primary))' }}
                      activeDot={{ r: 6, strokeWidth: 2, stroke: 'hsl(var(--card))' }} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Skill levels by re-score</CardTitle></CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted-foreground border-b">
                <th className="py-2 pr-4 font-medium">Skill</th>
                {series.map((s) => <th key={s.label} className="py-2 px-2 font-medium text-right tabular-nums">{s.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {Object.keys(latest.per_skill).map((skill) => (
                <tr key={skill} className="border-b last:border-0">
                  <td className="py-2 pr-4">{skill}</td>
                  {series.map((s) => (
                    <td key={s.label} className="py-2 px-2 text-right tabular-nums">{s.per_skill[skill]?.toFixed(1) ?? '—'}</td>
                  ))}
                </tr>
              ))}
              <tr className="font-medium">
                <td className="py-2 pr-4">Readiness</td>
                {series.map((s) => <td key={s.label} className="py-2 px-2 text-right tabular-nums">{Math.round(s.readiness)}%</td>)}
              </tr>
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardContent className="pt-5">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-2xl font-bold tabular-nums mt-1">{value}</p>
      </CardContent>
    </Card>
  );
}

/** Sessions this browser has started, with live readiness and what's next. */
function ActiveSessions() {
  const [items, setItems] = useState<SessionView[] | null>(null);

  useEffect(() => {
    const saved = savedSessions().slice(0, 3);
    Promise.all(saved.map((s) => coachApi.session(s.threadId).catch(() => null)))
      .then((views) => setItems(views.filter((v): v is SessionView => !!v)));
  }, []);

  if (!items?.length) return null;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Your coaching sessions</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {items.map((v) => {
          const w = v.waiting_for;
          const tab = w?.type === 'checkpoint' ? 'checkpoints' : w?.type === 'interview_question' ? 'interview' : 'plan';
          const next = v.done
            ? (v.state.status === 'ready' ? 'Interview-ready' : 'Coaching complete')
            : w?.type === 'checkpoint' ? `Next: ${w.skill} checkpoint`
            : w?.type === 'interview_question' ? `Next: interview question ${w.turn} of ${w.of}` : 'In progress';
          const gaps = v.state.skills.filter((s) => s.level < s.required_level).length;
          return (
            <div key={v.thread_id} className="flex flex-col sm:flex-row sm:items-center gap-3 rounded-lg border p-4">
              <div className="flex-1 min-w-0 space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold">{v.state.target_role}</span>
                  <Badge variant="secondary" className="font-normal">{next}</Badge>
                </div>
                <div className="flex items-center gap-3">
                  <ProgressBar value={v.readiness} className="h-2 flex-1" />
                  <span className="text-sm font-semibold tabular-nums w-12 text-right">{Math.round(v.readiness)}%</span>
                </div>
                <p className="text-xs text-muted-foreground">
                  Cycle {v.state.cycle + 1} of {v.state.max_cycles} · {gaps} skill gap{gaps === 1 ? '' : 's'} · target {v.state.target_readiness}%
                </p>
              </div>
              <Button asChild className="shrink-0">
                <Link to={`/session/${v.thread_id}/${v.done ? 'plan' : tab}`}>
                  {v.done ? 'View results' : 'Continue'} <ArrowRight className="h-4 w-4 ml-1" />
                </Link>
              </Button>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

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
