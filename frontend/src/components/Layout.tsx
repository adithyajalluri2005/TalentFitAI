import { Link, useLocation, useNavigate } from 'react-router-dom';
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
  ChevronRight,
  LogIn,
  LogOut,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext'; // ✅ Auth context

interface LayoutProps {
  children: React.ReactNode;
}

const navigationSequence = [
  { name: 'Dashboard', href: '/dashboard', icon: Home, step: 0 },
  { name: 'Process Resume', href: '/candidates/upload-resume', icon: Upload, step: 1 },
  { name: 'Match Job Descriptions', href: '/jobs/upload-jd', icon: FileText, step: 2 },
  { name: 'Skill Gap Analysis', href: '/skill-gap', icon: TrendingUp, step: 3 },
  { name: 'Create Assessment', href: '/assessments/create', icon: ClipboardList, step: 4 },
  { name: 'Interview Questions', href: '/interviews/questions', icon: MessageCircle, step: 5 },
];

export default function Layout({ children }: LayoutProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const { isAuthenticated, userRole, logout } = useAuth();

  const getCurrentStep = () => {
    const current = navigationSequence.find((nav) => nav.href === location.pathname);
    return current?.step ?? 0;
  };

  const getStepStatus = (step: number) => {
    const currentStep = getCurrentStep();
    if (step < currentStep) return 'completed';
    if (step === currentStep) return 'active';
    return 'upcoming';
  };

  // ✅ Handle login/logout logic
  const handleAuthAction = () => {
    if (isAuthenticated) {
      logout();              // clear auth state
      navigate('/login');    // go to login
    } else {
      navigate('/login');    // go to login
    }
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

            {/* Right side (status, role, login/logout) */}
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-success rounded-full"></div>
          

              {/* Role Badge */}
              {isAuthenticated && (
                <Badge
                  variant={userRole === 'admin' ? 'default' : 'secondary'}
                  className={`text-xs font-semibold ${
                    userRole === 'admin'
                      ? 'bg-indigo-600 hover:bg-indigo-700'
                      : ''
                  }`}
                >
                  {userRole?.toUpperCase()}
                </Badge>
              )}

              {/* Login / Logout Button */}
              <Button
                onClick={handleAuthAction}
                variant={isAuthenticated ? 'destructive' : 'default'}
                size="sm"
                className="ml-2"
              >
                {isAuthenticated ? (
                  <>
                    <LogOut className="w-4 h-4 mr-1" />
                    Logout
                  </>
                ) : (
                  <>
                    <LogIn className="w-4 h-4 mr-1" />
                    Login
                  </>
                )}
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Progress Navigation — ❌ Hidden for Admin users */}
      {isAuthenticated && userRole !== 'admin' && (
        <nav className="border-b border-border bg-muted/30">
          <div className="container mx-auto px-4 py-3">
            <div className="flex items-center gap-1 overflow-x-auto">
              {navigationSequence.map((item, index) => {
                const Icon = item.icon;
                const status = getStepStatus(item.step);
                const isActive = location.pathname === item.href;

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
      )}

      {/* Main content */}
      <main className="container mx-auto px-4 py-8">{children}</main>
    </div>
  );
}
