import { Link, useLocation } from 'react-router-dom';
import {
  Users,
  TrendingUp,
  ClipboardList,
  MessageCircle,
  Upload,
  Home,
  ChevronRight,
} from 'lucide-react';
import { savedSessions } from '@/services/coach';

interface LayoutProps {
  children: React.ReactNode;
}

// Steps 2-4 belong to a coaching session; `href` receives its thread id.
const navigationSequence = [
  { name: 'Dashboard', href: () => '/dashboard', icon: Home, step: 0, needsSession: false },
  { name: 'Resume & Role', href: () => '/start', icon: Upload, step: 1, needsSession: false },
  { name: 'Skill Gap & Topics', href: (id: string) => `/session/${id}/plan`, icon: TrendingUp, step: 2, needsSession: true },
  { name: 'Assessments', href: (id: string) => `/session/${id}/checkpoints`, icon: ClipboardList, step: 3, needsSession: true },
  { name: 'Final Interview', href: (id: string) => `/session/${id}/interview`, icon: MessageCircle, step: 4, needsSession: true },
];

const SESSION_TAB_STEP: Record<string, number> = { plan: 2, checkpoints: 3, interview: 4 };

export default function Layout({ children }: LayoutProps) {
  const location = useLocation();

  // The session the tabs point at: the one being viewed, else the most recent.
  const sessionMatch = location.pathname.match(/^\/session\/([^/]+)(?:\/([^/]+))?/);
  const threadId = sessionMatch?.[1] ?? savedSessions()[0]?.threadId;

  const getCurrentStep = () => {
    if (sessionMatch) return SESSION_TAB_STEP[sessionMatch[2] ?? 'plan'] ?? 2;
    if (location.pathname.startsWith('/start')) return 1;
    return 0;
  };

  const getStepStatus = (step: number) => {
    const currentStep = getCurrentStep();
    if (step < currentStep) return 'completed';
    if (step === currentStep) return 'active';
    return 'upcoming';
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-card/50 backdrop-blur supports-[backdrop-filter]:bg-card/50">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            {/* Logo */}
            <div className="flex items-center">
              <div className="w-8 h-8 bg-gradient-primary rounded-lg flex items-center justify-center">
                <Users className="h-5 w-5 text-primary-foreground" />
              </div>
              <span className="ml-2 text-lg font-semibold text-foreground">
                TalentFitAI
              </span>
            </div>

            {/* Right side (status) */}
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-success rounded-full"></div>
            </div>
          </div>
        </div>
      </header>

      {/* Progress Navigation */}
      <nav className="border-b border-border bg-muted/30">
        <div className="container mx-auto px-4 py-3">
          <div className="flex items-center gap-1 overflow-x-auto">
            {navigationSequence.map((item, index) => {
              const Icon = item.icon;
              const status = getStepStatus(item.step);
              const disabled = item.needsSession && !threadId;
              const className = `flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${
                status === 'active'
                  ? 'bg-primary text-primary-foreground'
                  : status === 'completed'
                  ? 'bg-success/10 text-success hover:bg-success/20'
                  : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
              } ${disabled ? 'opacity-50 pointer-events-none' : ''}`;
              const content = (
                <>
                  <Icon className="h-4 w-4" />
                  <span className="hidden sm:inline">{item.name}</span>
                  <div
                    className={`w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold ${
                      status === 'active'
                        ? 'bg-primary-foreground text-primary'
                        : status === 'completed'
                        ? 'bg-success text-success-foreground'
                        : 'bg-muted text-muted-foreground'
                    }`}
                  >
                    {item.step + 1}
                  </div>
                </>
              );

              return (
                <div key={item.name} className="flex items-center gap-1 flex-shrink-0">
                  {disabled ? (
                    <span className={className} aria-disabled="true" title="Start a coaching session first">{content}</span>
                  ) : (
                    <Link to={item.href(threadId ?? '')} className={className}>{content}</Link>
                  )}
                  {index < navigationSequence.length - 1 && (
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </nav>

      {/* Main content */}
      <main className="container mx-auto px-4 py-8">{children}</main>
    </div>
  );
}
