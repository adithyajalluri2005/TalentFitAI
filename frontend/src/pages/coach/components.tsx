import { useState } from 'react';
import { ChevronDown } from 'lucide-react';
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
