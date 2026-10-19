import { useState } from 'react';
import { BadgeCheck, ChevronDown, ExternalLink, Sparkles } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { SkillLevel } from '@/services/coach';

export function ReadinessRing({ value, target, size = 140 }: { value: number; target: number; size?: number }) {
  const stroke = 12;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(value, 100));
  const color = pct >= target ? 'hsl(var(--success))' : pct >= target * 0.6 ? 'hsl(var(--primary))' : 'hsl(var(--warning))';
  const targetAngle = (target / 100) * 2 * Math.PI - Math.PI / 2;
  const cx = size / 2;
  return (
    <svg width={size} height={size} role="img" aria-label={`Readiness ${Math.round(pct)} percent, target ${target}`}>
      <circle cx={cx} cy={cx} r={r} fill="none" stroke="hsl(var(--muted))" strokeWidth={stroke} />
      <circle
        cx={cx} cy={cx} r={r} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round"
        strokeDasharray={c} strokeDashoffset={c * (1 - pct / 100)} transform={`rotate(-90 ${cx} ${cx})`}
        style={{ transition: 'stroke-dashoffset 0.8s ease' }}
      />
      {/* target marker: a notch sitting exactly on the track */}
      <line
        x1={cx + (r - stroke / 2) * Math.cos(targetAngle)} y1={cx + (r - stroke / 2) * Math.sin(targetAngle)}
        x2={cx + (r + stroke / 2) * Math.cos(targetAngle)} y2={cx + (r + stroke / 2) * Math.sin(targetAngle)}
        stroke="hsl(var(--card))" strokeWidth={4}
      />
      <line
        x1={cx + (r - stroke / 2) * Math.cos(targetAngle)} y1={cx + (r - stroke / 2) * Math.sin(targetAngle)}
        x2={cx + (r + stroke / 2) * Math.cos(targetAngle)} y2={cx + (r + stroke / 2) * Math.sin(targetAngle)}
        stroke="hsl(var(--foreground))" strokeWidth={2} strokeLinecap="round"
      />
      <text x="50%" y="48%" textAnchor="middle" className="fill-foreground" style={{ fontSize: size / 4.5, fontWeight: 700 }}>
        {Math.round(pct)}%
      </text>
      <text x="50%" y="64%" textAnchor="middle" className="fill-muted-foreground" style={{ fontSize: size / 12 }}>
        target {target}%
      </text>
    </svg>
  );
}

const SOURCE_LABEL = { resume: 'Resume', checkpoint: 'Checkpoint', interview: 'Interview' } as const;

export function SkillRow({ skill }: { skill: SkillLevel }) {
  const [open, setOpen] = useState(false);
  const met = skill.level >= skill.required_level;
  return (
    <div className="py-2">
      <button type="button" className="w-full text-left" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <div className="flex items-center justify-between text-sm mb-1.5 gap-2">
          <span className="font-medium truncate">{skill.skill}</span>
          <span className="flex items-center gap-1 text-muted-foreground tabular-nums shrink-0">
            {skill.level.toFixed(1)} / {skill.required_level}
            <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', open && 'rotate-180')} />
          </span>
        </div>
        <div className="relative h-2 rounded-full bg-muted">
          <div
            className={cn('absolute inset-y-0 left-0 rounded-full transition-all duration-700', met ? 'bg-success' : 'bg-primary')}
            style={{ width: `${(skill.level / 5) * 100}%` }}
          />
          <div className="absolute -top-1 -bottom-1 w-0.5 bg-foreground" style={{ left: `${(skill.required_level / 5) * 100}%` }} />
        </div>
      </button>
      {open && (
        <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
          {skill.observations.map((o, i) => (
            <li key={i} className="flex gap-2">
              <Badge variant="outline" className="h-5 shrink-0 text-[10px]">{SOURCE_LABEL[o.source]}</Badge>
              <span><span className="font-medium text-foreground">{o.value.toFixed(1)}</span> — {o.note || 'no evidence found'}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * Question text that may contain Markdown code: ```fenced blocks``` become
 * code blocks and `inline code` becomes code spans. Everything else is plain
 * text (no HTML is ever interpreted).
 */
export function CodeText({ text, className }: { text: string; className?: string }) {
  const parts = text.split(/```[\w+-]*\n?([\s\S]*?)```/g);
  return (
    <div className={cn('space-y-2', className)}>
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <pre key={i} className="rounded-md bg-muted px-3 py-2 text-xs font-mono overflow-x-auto whitespace-pre">
            {part.replace(/\n$/, '')}
          </pre>
        ) : part.trim() ? (
          <span key={i} className="block whitespace-pre-wrap">
            {part.split(/`([^`]+)`/g).map((bit, j) =>
              j % 2 === 1 ? <code key={j} className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]">{bit}</code> : bit,
            )}
          </span>
        ) : null,
      )}
    </div>
  );
}

// Known interview-prep sites get their own colour; anything else uses the theme colour.
const SITE_STYLE: Record<string, { short: string; badge: string }> = {
  'geeksforgeeks.org': { short: 'GfG', badge: 'bg-emerald-600 text-white' },
  'interviewbit.com': { short: 'IB', badge: 'bg-sky-600 text-white' },
};

function siteOf(url: string): { host: string; path: string } {
  try {
    const u = new URL(url);
    const path = decodeURIComponent(u.pathname).replace(/\/+$/, '').split('/').filter(Boolean).pop() ?? '';
    return { host: u.hostname.replace(/^www\./, ''), path: path.replace(/[-_]+/g, ' ') };
  } catch {
    return { host: url, path: '' };
  }
}

/**
 * Where a question comes from, as a small source card: the site's badge, its
 * name, the page it was taken from and a "verified" mark (web questions are
 * kept only when their answer is quoted on that page). Model-written
 * questions get an "AI-generated" chip instead.
 *
 * tone="dark" is for the interview's dark call screen.
 */
export function SourceLink({ name, url, label = 'Source', tone = 'light', className }: {
  name?: string; url?: string; label?: string; tone?: 'light' | 'dark'; className?: string;
}) {
  const dark = tone === 'dark';
  if (!url) {
    return (
      <span className={cn('inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px]',
        dark ? 'border-slate-700 bg-slate-800/80 text-slate-300' : 'border-dashed bg-muted/50 text-muted-foreground', className)}>
        <Sparkles className="h-3 w-3" /> AI-generated question
      </span>
    );
  }
  const { host, path } = siteOf(url);
  const style = SITE_STYLE[host];
  const site = name || host;
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      title={`${label}: ${site} (${url})`}
      className={cn(
        'group inline-flex max-w-full items-center gap-2 rounded-lg border py-1 pl-1 pr-2.5 text-xs transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary',
        dark ? 'border-slate-700 bg-slate-800/80 text-slate-100 hover:border-sky-400/60 hover:bg-slate-800'
          : 'bg-card hover:border-primary/50 hover:bg-primary/5 shadow-sm',
        className,
      )}
    >
      <span className={cn('flex h-6 min-w-6 shrink-0 items-center justify-center rounded-md px-1 text-[10px] font-bold',
        style?.badge ?? 'bg-primary text-primary-foreground')}>
        {style?.short ?? site.slice(0, 2).toUpperCase()}
      </span>
      <span className="min-w-0 leading-tight">
        <span className={cn('block text-[10px] uppercase tracking-wide', dark ? 'text-slate-400' : 'text-muted-foreground')}>{label}</span>
        <span className="flex items-center gap-1 font-medium">
          <span className="truncate">{site}</span>
          {path && <span className={cn('hidden truncate font-normal sm:inline', dark ? 'text-slate-400' : 'text-muted-foreground')}>· {path}</span>}
        </span>
      </span>
      <span className={cn('flex shrink-0 items-center gap-0.5 text-[10px] font-medium', dark ? 'text-emerald-400' : 'text-success')}
            title="The answer is quoted on this page">
        <BadgeCheck className="h-3.5 w-3.5" /> <span className="hidden sm:inline">Verified</span>
      </span>
      <ExternalLink className={cn('h-3.5 w-3.5 shrink-0 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5',
        dark ? 'text-slate-400' : 'text-muted-foreground group-hover:text-primary')} />
    </a>
  );
}
