import { Link, useLocation } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Users,
  FileText,
  Target,
  TrendingUp,
  ClipboardList,
  MessageCircle,
  Upload,
  Home,
  ChevronRight
} from 'lucide-react';

interface LayoutProps {
  children: React.ReactNode;
}

const navigationSequence = [
  { name: 'Dashboard', href: '/dashboard', icon: Home, step: 0 },
  { name: 'Upload Resume', href: '/candidates/upload-resume', icon: Upload, step: 1 },
  { name: 'Upload Job Description', href: '/jobs/upload-jd', icon: FileText, step: 2 },
  { name: 'Matching', href: '/matching', icon: Target, step: 3 },
  { name: 'Skill Gap Analysis', href: '/skill-gap', icon: TrendingUp, step: 4 },
  { name: 'Create Assessment', href: '/assessments/create', icon: ClipboardList, step: 5 },
  { name: 'Interview Questions', href: '/interviews/questions', icon: MessageCircle, step: 6 },
];

export default function Layout({ children }: LayoutProps) {
  const location = useLocation();
  
  const getCurrentStep = () => {
    const current = navigationSequence.find(nav => nav.href === location.pathname);
    return current?.step ?? 0;
  };

  const getStepStatus = (step: number) => {
    const currentStep = getCurrentStep();
    if (step < currentStep) return 'completed';
    if (step === currentStep) return 'active';
    return 'upcoming';
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Header Navigation */}
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

            {/* API Status */}
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-success rounded-full"></div>
              <Badge variant="secondary" className="text-xs">
                Online
              </Badge>
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
              const isActive = location.pathname === item.href;
              const status = getStepStatus(item.step);
              
              return (
                <div key={item.name} className="flex items-center gap-1 flex-shrink-0">
                  <Link
                    to={item.href}
                    className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${
                      status === 'active'
                        ? 'bg-primary text-primary-foreground'
                        : status === 'completed'
                        ? 'bg-success/10 text-success hover:bg-success/20'
                        : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                    <span className="hidden sm:inline">{item.name}</span>
                    <div className={`w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold ${
                      status === 'active'
                        ? 'bg-primary-foreground text-primary'
                        : status === 'completed'
                        ? 'bg-success text-success-foreground'
                        : 'bg-muted text-muted-foreground'
                    }`}>
                      {item.step + 1}
                    </div>
                  </Link>
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
      <main className="container mx-auto px-4 py-8">
        {children}
      </main>
    </div>
  );
}