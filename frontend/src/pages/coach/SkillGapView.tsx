import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Progress } from '@/components/ui/progress';
import {
  TrendingUp,
  ExternalLink,
  BookOpen,
  FileText,
  GraduationCap,
  PlayCircle,
  Github,
  ClipboardList,
  CheckCircle2,
  Lock,
  Video,
  Star,
  AlertCircle,
  Sparkles,
} from 'lucide-react';
import { Resource, SessionView } from '@/services/coach';
import { cn } from '@/lib/utils';

// Same structure as the original Skill Gap Analysis page, fed by the coaching session.

const RESOURCE_STYLE: Record<string, { icon: typeof BookOpen; label: string; tile: string }> = {
  docs: { icon: BookOpen, label: 'Docs', tile: 'bg-primary/10 text-primary' },
  video: { icon: PlayCircle, label: 'Video', tile: 'bg-red-500/10 text-red-600 dark:text-red-400' },
  course: { icon: GraduationCap, label: 'Course', tile: 'bg-violet-500/10 text-violet-600 dark:text-violet-400' },
  github: { icon: Github, label: 'GitHub', tile: 'bg-foreground/10 text-foreground' },
  article: { icon: FileText, label: 'Article', tile: 'bg-muted text-muted-foreground' },
};

function ResourceRow({ resource }: { resource: Resource }) {
  const style = RESOURCE_STYLE[resource.type] ?? RESOURCE_STYLE.article;
  const Icon = style.icon;
  const detail = resource.meta || resource.source;
  return (
    <a
      href={resource.url.trim()}
      target="_blank"
      rel="noreferrer"
      className="group flex items-center gap-3 p-2 rounded-lg hover:bg-muted/60 transition-colors"
    >
      <span className={cn('flex h-8 w-8 shrink-0 items-center justify-center rounded-md', style.tile)}>
        <Icon className="h-4 w-4" />
      </span>
      <span className="flex-1 min-w-0">
        <span className="text-sm font-medium line-clamp-2 sm:line-clamp-1 break-words group-hover:text-primary" title={resource.title}>
          {resource.title}
        </span>
        <span className="block text-xs text-muted-foreground truncate">
          {style.label}{detail && ` · ${detail}`}
        </span>
      </span>
      <ExternalLink className="h-3.5 w-3.5 shrink-0 text-muted-foreground opacity-50 group-hover:opacity-100" />
    </a>
  );
}

function Stat({ icon: Icon, value, label, tone }: {
  icon: typeof Star;
  value: string | number;
  label: string;
  tone: string;
}) {
  return (
    <Card>
      <CardContent className="p-3 sm:p-4 text-center">
        <Icon className={cn('h-6 w-6 sm:h-8 sm:w-8 mx-auto mb-1 sm:mb-2', tone)} />
        <p className={cn('text-xl sm:text-2xl font-bold tabular-nums', tone)}>{value}</p>
        <p className="text-xs sm:text-sm text-muted-foreground">{label}</p>
      </CardContent>
    </Card>
  );
}

export default function SkillGapView({ view, onTick, onAssess, onInterview }: {
  view: SessionView;
  /** tick / untick a study topic */
  onTick?: (skill: string, topicIndex: number, done: boolean) => void;
  /** open (or switch to) this skill's assessment */
  onAssess?: (skill: string) => void;
  onInterview?: () => void;
}) {
  const { state, waiting_for: waiting } = view;
  const matchedSkills = state.skills.filter((s) => s.level >= s.required_level);
  const missingSkills = state.skills.filter((s) => s.level < s.required_level);
  const plan = state.plan;
  const topicDone = view.topic_done ?? {};
  // Skills still awaiting their assessment this cycle, and results for the ones taken.
  const pending = waiting?.type === 'checkpoint' ? waiting.pending ?? [waiting.skill] : [];
  const assessed = new Map(
    state.checkpoints.filter((c) => c.cycle === state.cycle).map((c) => [c.skill, c] as const),
  );

  return (
    <div className="space-y-6">
      {/* Current Status */}
      <div className="grid grid-cols-3 gap-3 sm:gap-4">
        <Stat icon={Star} value={matchedSkills.length} label="Matched Skills" tone="text-success" />
        <Stat icon={AlertCircle} value={missingSkills.length} label="Missing Skills" tone="text-warning" />
        <Stat icon={TrendingUp} value={`${Math.round(view.readiness)}%`} label="Readiness" tone="text-primary" />
      </div>

      {/* Analysis Section */}
      <Card>
        <CardHeader className="px-4 sm:px-6">
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-primary" />
            Your Learning Path
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            Personalized topics and hand-picked free resources to close each gap, most important first.
          </p>
        </CardHeader>
        <CardContent className="px-4 sm:px-6">
          {plan.length === 0 ? (
            <div className="text-center py-8 space-y-2">
              <Star className="h-16 w-16 mx-auto text-success" />
              <p className="text-sm text-success">All required skills matched! Proceed to the mock interview.</p>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Priority Skills */}
              <div>
                <h3 className="font-semibold mb-3 flex items-center gap-2">
                  <Star className="h-4 w-4" />
                  Priority Skills to Develop
                </h3>
                <div className="flex flex-wrap gap-2">
                  {plan.map((p) => {
                    const s = state.skills.find((k) => k.skill === p.skill);
                    return (
                      <Badge key={p.skill} variant="default" className="bg-warning/10 text-warning border-warning/30 hover:bg-warning/20">
                        {p.skill}
                        {s && <span className="ml-1.5 font-normal opacity-80 tabular-nums">{s.level.toFixed(1)} → {s.required_level}</span>}
                      </Badge>
                    );
                  })}
                </div>
              </div>

              {/* Learning Resources */}
              <div>
                <h3 className="font-semibold mb-1">Recommended Learning Resources</h3>
                <p className="text-sm text-muted-foreground mb-4">
                  Tick each topic once you've studied it. When every topic of a skill is ticked, its assessment unlocks.
                </p>
                <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                  {plan.map((p) => {
                    const skillWide = p.resources ?? [];
                    const ticked = new Set(topicDone[p.skill] ?? []);
                    const doneCount = p.topics.filter((_, i) => ticked.has(i)).length;
                    const allTicked = p.topics.length > 0 && doneCount === p.topics.length;
                    const result = assessed.get(p.skill);
                    const isPending = pending.includes(p.skill);
                    return (
                      <Card
                        key={p.skill}
                        className={cn(
                          'min-w-0 hover:shadow-md transition-shadow',
                          result && !result.skipped && 'border-success/50',
                          !result && allTicked && isPending && 'border-primary/60 ring-1 ring-primary/30',
                        )}
                      >
                        <CardHeader className="pb-3 px-3 sm:px-6 space-y-2">
                          <CardTitle className="text-base flex items-center justify-between gap-2">
                            <span className="min-w-0">{p.skill}</span>
                            {result && !result.skipped ? (
                              <Badge className="text-xs shrink-0 bg-success/10 text-success border-success/30 hover:bg-success/10">
                                <CheckCircle2 className="h-3 w-3 mr-1" /> Assessed · {Math.round(result.score * 100)}%
                              </Badge>
                            ) : (
                              <Badge variant="outline" className="text-xs shrink-0 tabular-nums">{doneCount}/{p.topics.length} topics</Badge>
                            )}
                          </CardTitle>
                          {!result && <Progress value={p.topics.length ? (doneCount / p.topics.length) * 100 : 0} className="h-1.5" />}
                        </CardHeader>
                        <CardContent className="space-y-4 px-2 sm:px-6">
                          {skillWide.length > 0 && (
                            <div className="rounded-lg bg-primary/5 border border-primary/15 p-1.5">
                              <p className="text-[11px] font-semibold text-primary uppercase tracking-wide px-2 pt-1">Start here</p>
                              {skillWide.map((r, i) => <ResourceRow key={i} resource={r} />)}
                            </div>
                          )}
                          {p.topics.map((t, i) => {
                            const checked = ticked.has(i);
                            const id = `topic-${p.skill}-${i}`.replace(/\W+/g, '-');
                            return (
                              <div key={i}>
                                <div className="flex items-start gap-2.5 px-2 mb-1">
                                  <Checkbox
                                    id={id}
                                    checked={checked}
                                    disabled={!!result || !onTick}
                                    onCheckedChange={(v) => onTick?.(p.skill, i, v === true)}
                                    className="mt-0.5"
                                  />
                                  <label
                                    htmlFor={id}
                                    className={cn('text-sm font-medium leading-snug cursor-pointer min-w-0',
                                      checked && 'text-muted-foreground line-through decoration-muted-foreground/50')}
                                  >
                                    {i + 1}. {t.title}
                                  </label>
                                </div>
                                {t.resources.length > 0 ? (
                                  <div className="pl-6">{t.resources.map((r, j) => <ResourceRow key={j} resource={r} />)}</div>
                                ) : (
                                  <p className="text-xs text-muted-foreground pl-9 pb-1">Covered by the course above</p>
                                )}
                              </div>
                            );
                          })}

                          {/* assessment gate */}
                          {!result && isPending && (
                            <div className="pt-1 px-2">
                              {allTicked ? (
                                <Button className="w-full" onClick={() => onAssess?.(p.skill)} disabled={!onAssess}>
                                  <ClipboardList className="h-4 w-4 mr-2" /> Take {p.skill} assessment
                                </Button>
                              ) : (
                                <p className="flex items-center justify-center gap-2 rounded-md border border-dashed py-2.5 text-xs text-muted-foreground">
                                  <Lock className="h-3.5 w-3.5" /> Tick all {p.topics.length} topics to unlock the assessment
                                </p>
                              )}
                            </div>
                          )}
                          {result?.skipped && (
                            <p className="text-xs text-muted-foreground text-center">Assessment skipped</p>
                          )}
                        </CardContent>
                      </Card>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* Final interview gate */}
          {!view.done && (
            <div className="pt-4 mt-6 border-t">
              {waiting?.type === 'interview_question' ? (
                <Button onClick={onInterview} className="w-full" disabled={!onInterview}>
                  <Video className="h-4 w-4 mr-2" /> Start final interview (camera + mic)
                </Button>
              ) : (
                <div className="flex items-center gap-3 rounded-lg border border-dashed p-4">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-muted">
                    <Lock className="h-4 w-4 text-muted-foreground" />
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm font-medium">Final interview · camera + mic</p>
                    <p className="text-xs text-muted-foreground">
                      Unlocks after every skill assessment ({plan.length - pending.length}/{plan.length} done).
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
