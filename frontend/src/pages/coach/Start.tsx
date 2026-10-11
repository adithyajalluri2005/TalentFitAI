import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, FileText, Loader2, Sparkles, Upload, History } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/hooks/use-toast';
import {
  coachApi, errorMessage, getCandidateId, rememberSession, savedSessions,
  RoleProfile, RoleSuggestion,
} from '@/services/coach';
import { cn } from '@/lib/utils';

const START_STAGES = [
  'Reading your resume…',
  'Rating each skill against the role…',
  'Picking topics and searching for the best sources…',
  'Curating sources…',
  'Writing your first checkpoint…',
];

export default function Start() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const fileInput = useRef<HTMLInputElement>(null);

  const [resume, setResume] = useState<File | null>(null);
  const [roles, setRoles] = useState<RoleProfile[]>([]);
  const [suggestions, setSuggestions] = useState<RoleSuggestion[] | null>(null);
  const [suggesting, setSuggesting] = useState(false);
  const [mode, setMode] = useState<'role' | 'jd'>('role');
  const [roleSlug, setRoleSlug] = useState<string | null>(null);
  const [jdText, setJdText] = useState('');
  const [jdRole, setJdRole] = useState('');
  const [turns, setTurns] = useState(5);
  const [starting, setStarting] = useState(false);
  const [stage, setStage] = useState(0);

  const previous = useMemo(() => savedSessions(), []);

  useEffect(() => {
    coachApi.roles().then(setRoles).catch((e) =>
      toast({ title: 'Could not load roles', description: errorMessage(e), variant: 'destructive' }));
  }, [toast]);

  useEffect(() => {
    if (!starting) return;
    const t = setInterval(() => setStage((s) => Math.min(s + 1, START_STAGES.length - 1)), 9000);
    return () => clearInterval(t);
  }, [starting]);

  const suggestionFor = (slug: string) => suggestions?.find((s) => s.slug === slug);
  const orderedRoles = suggestions
    ? [...roles].sort((a, b) => (suggestionFor(b.slug)?.readiness ?? 0) - (suggestionFor(a.slug)?.readiness ?? 0))
    : roles;

  const pickFile = (f: File | undefined) => {
    if (!f) return;
    if (f.type !== 'application/pdf') {
      toast({ title: 'PDF only', description: 'Please upload your resume as a PDF.', variant: 'destructive' });
      return;
    }
    setResume(f);
    setSuggestions(null);
  };

  const suggest = async () => {
    if (!resume) return;
    setSuggesting(true);
    try {
      const s = await coachApi.suggestRoles(resume);
      setSuggestions(s);
      if (!roleSlug && s[0]) setRoleSlug(s[0].slug);
    } catch (e) {
      toast({ title: 'Could not compare roles', description: errorMessage(e), variant: 'destructive' });
    } finally {
      setSuggesting(false);
    }
  };

  const canStart = !!resume && (mode === 'role' ? !!roleSlug : jdText.trim().length > 50);

  const start = async () => {
    if (!resume || !canStart) return;
    setStarting(true);
    setStage(0);
    try {
      const view = await coachApi.start({
        candidateId: getCandidateId(),
        resume,
        roleSlug: mode === 'role' ? roleSlug! : undefined,
        jdText: mode === 'jd' ? jdText : undefined,
        targetRole: mode === 'jd' ? jdRole : undefined,
        interviewTurns: turns,
      });
      rememberSession({ threadId: view.thread_id, role: view.state.target_role, startedAt: new Date().toISOString() });
      navigate(`/session/${view.thread_id}/plan`);
    } catch (e) {
      toast({ title: 'Could not start coaching', description: errorMessage(e), variant: 'destructive' });
      setStarting(false);
    }
  };

  if (starting) {
    return (
      <div className="max-w-md mx-auto py-24 text-center space-y-4">
        <Loader2 className="h-10 w-10 animate-spin text-primary mx-auto" />
        <h2 className="text-xl font-semibold">Setting up your coaching plan</h2>
        <p className="text-muted-foreground">{START_STAGES[stage]}</p>
        <p className="text-xs text-muted-foreground">This usually takes about a minute.</p>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <section className="text-center space-y-3 pt-4">
        <h1 className="text-3xl md:text-4xl font-bold tracking-tight">Get interview-ready for your target role</h1>
        <p className="text-muted-foreground max-w-2xl mx-auto">
          Your AI career coach finds your skill gaps, hand-picks free docs, videos, courses and repos to close them,
          checks your progress, and runs a mock voice interview — then re-scores you and adapts.
        </p>
      </section>

      {previous.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2"><History className="h-4 w-4" /> Continue where you left off</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {previous.slice(0, 4).map((s) => (
              <Button key={s.threadId} variant="outline" size="sm" asChild>
                <Link to={`/session/${s.threadId}/plan`}>
                  {s.role || 'Coaching session'} · {new Date(s.startedAt).toLocaleDateString()}
                </Link>
              </Button>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Step 1 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">1. Your resume</CardTitle>
          <CardDescription>PDF with selectable text. It is only used for this coaching session.</CardDescription>
        </CardHeader>
        <CardContent>
          <button
            type="button"
            onClick={() => fileInput.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); pickFile(e.dataTransfer.files[0]); }}
            className="w-full border-2 border-dashed border-border rounded-lg p-8 flex flex-col items-center gap-2 hover:border-primary hover:bg-primary/5 transition-colors"
          >
            {resume ? (
              <>
                <FileText className="h-8 w-8 text-primary" />
                <span className="font-medium">{resume.name}</span>
                <span className="text-xs text-muted-foreground">Click to replace</span>
              </>
            ) : (
              <>
                <Upload className="h-8 w-8 text-muted-foreground" />
                <span className="font-medium">Drop your resume here or click to browse</span>
              </>
            )}
          </button>
          <input ref={fileInput} type="file" accept="application/pdf" className="hidden"
                 onChange={(e) => pickFile(e.target.files?.[0])} />
        </CardContent>
      </Card>

      {/* Step 2 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">2. Your target</CardTitle>
          <CardDescription>Pick a role track, or paste a specific job posting.</CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs value={mode} onValueChange={(v) => setMode(v as 'role' | 'jd')}>
            <TabsList className="mb-4">
              <TabsTrigger value="role">Role track</TabsTrigger>
              <TabsTrigger value="jd">I have a job posting</TabsTrigger>
            </TabsList>

            <TabsContent value="role" className="space-y-4">
              <div className="flex flex-wrap items-center gap-3">
                <Button variant="secondary" onClick={suggest} disabled={!resume || suggesting}>
                  {suggesting ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Sparkles className="h-4 w-4 mr-2" />}
                  Which role suits me?
                </Button>
                {!resume && <span className="text-sm text-muted-foreground">Upload your resume first</span>}
              </div>

              <div className="grid sm:grid-cols-2 gap-3">
                {orderedRoles.map((r) => {
                  const s = suggestionFor(r.slug);
                  const selected = roleSlug === r.slug;
                  return (
                    <button
                      key={r.slug}
                      type="button"
                      onClick={() => setRoleSlug(r.slug)}
                      className={cn(
                        'text-left rounded-lg border p-4 transition-colors space-y-2',
                        selected ? 'border-primary bg-primary/5 ring-1 ring-primary' : 'border-border hover:border-primary/50',
                      )}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <span className="font-semibold">{r.title}</span>
                        {s && (
                          <Badge variant={s.readiness >= 60 ? 'default' : 'secondary'}>{Math.round(s.readiness)}% ready</Badge>
                        )}
                      </div>
                      <p className="text-sm text-muted-foreground">{r.description}</p>
                      {s ? (
                        <div className="text-xs space-y-1">
                          {s.strengths.length > 0 && <p><span className="text-success font-medium">Strong:</span> {s.strengths.join(', ')}</p>}
                          {s.top_gaps.length > 0 && (
                            <p><span className="text-warning font-medium">Work on:</span> {s.top_gaps.map((g) => g.skill).join(', ')}</p>
                          )}
                        </div>
                      ) : (
                        <p className="text-xs text-muted-foreground">{r.skills.slice(0, 5).map((k) => k.skill).join(' · ')}</p>
                      )}
                    </button>
                  );
                })}
              </div>
            </TabsContent>

            <TabsContent value="jd" className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="jd-role">Role title (optional)</Label>
                <Input id="jd-role" placeholder="e.g. Associate Software Engineer" value={jdRole} onChange={(e) => setJdRole(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="jd">Job description</Label>
                <Textarea id="jd" rows={8} placeholder="Paste the full job description…" value={jdText} onChange={(e) => setJdText(e.target.value)} />
              </div>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>

      {/* Step 3 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">3. Mock interview</CardTitle>
        </CardHeader>
        <CardContent className="max-w-sm">
          <div className="space-y-3">
            <Label>Mock interview length: <span className="font-semibold">{turns} questions</span></Label>
            <Slider min={2} max={8} step={1} value={[turns]} onValueChange={([v]) => setTurns(v)} />
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end pb-8">
        <Button size="lg" onClick={start} disabled={!canStart}>
          Start coaching <ArrowRight className="h-4 w-4 ml-2" />
        </Button>
      </div>
    </div>
  );
}
