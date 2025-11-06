import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import {
  Target,
  TrendingUp,
  Upload,
  CheckCircle,
  AlertCircle,
  Clock,
  Send,
  FileText,
  ChevronRight,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { CandidateState } from '@/services/api';
import { useToast } from '@/hooks/use-toast';
import { useMemo } from 'react';


export default function Dashboard() {
  const [currentSession, setCurrentSession] = useState<{
    threadId?: string;
    state?: CandidateState;
    progress: number;
  }>({ progress: 0 });

  const { toast } = useToast();

  useEffect(() => {
    const stored = localStorage.getItem('talentai-session');
    if (stored) {
      try {
        const session = JSON.parse(stored);
        setCurrentSession(session);
      } catch (error) {
        console.error('Failed to load session:', error);
      }
    }
  }, []);

  const getProgressPhase = () => {
    if (!currentSession.state) return 'Start by uploading a resume';
    if (!currentSession.state.candidate_skills.length) return 'Resume processing...';
    if (!currentSession.state.jd_text) return 'Find best job match';
    if (currentSession.state.match_score === 0) return 'Analyzing match score...';
    if (!currentSession.state.skill_resources || Object.keys(currentSession.state.skill_resources).length === 0)
      return 'Analyze skill gaps';
    if (!currentSession.state.mcqs.length) return 'Generate assessment';
    if (!currentSession.state.interview_questions.length) return 'Generate interview questions';
    if (currentSession.state.feedback) return 'Evaluation complete';
    return 'Continue candidate evaluation';
  };

  const progressValue = useMemo(() => {
  const s = currentSession.state;
  if (!s) return 0;

  // safe helpers
  const hasArray = (a: any) => Array.isArray(a) && a.length > 0;
  const hasObjectKeys = (o: any) => o && typeof o === 'object' && Object.keys(o).length > 0;
  const positiveNumber = (n: any) => typeof n === 'number' && !Number.isNaN(n) && n > 0;

  let progress = 0;
  // Weights mirror the workflow importance (total = 100)
  if (hasArray(s.candidate_skills)) progress += 15;        // resume uploaded / skills extracted
  if (s.jd_text && s.jd_text.trim().length > 0) progress += 20; // JD matched / JD text present
  if (positiveNumber(s.match_score)) progress += 15;       // match score computed
  if (hasObjectKeys(s.skill_resources)) progress += 15;    // skill resources produced
  if (hasArray(s.mcqs)) progress += 10;                    // assessments generated
  if (hasArray(s.interview_questions)) progress += 15;     // interview questions ready
  if (s.feedback && typeof s.feedback === 'string' && s.feedback.trim().length > 0) progress += 10; // final feedback

  // Guarantee 0..100
  return Math.min(100, Math.max(0, Math.round(progress)));
}, [currentSession.state]);
  const stats = [
    {
      name: 'Match Score',
      value: currentSession.state
        ? `${Math.round((currentSession.state.match_score || 0) * 100)}%`
        : '0%',
      icon: Target,
      change:
        currentSession.state && currentSession.state.match_score > 0.7
          ? 'Excellent Fit'
          : currentSession.state && currentSession.state.match_score > 0.4
          ? 'Moderate Fit'
          : 'Needs Improvement',
      color:
        currentSession.state && currentSession.state.match_score > 0.7
          ? 'text-green-600'
          : currentSession.state && currentSession.state.match_score > 0.4
          ? 'text-yellow-600'
          : 'text-red-600',
    },
    {
      name: 'Skills Identified',
      value: currentSession.state ? currentSession.state.candidate_skills.length : 0,
      icon: CheckCircle,
      change: 'From uploaded resume',
    },
    {
      name: 'Missing Skills',
      value: currentSession.state ? (currentSession.state.missing_skills || []).length : 0,
      icon: AlertCircle,
      change:
        currentSession.state && (currentSession.state.missing_skills || []).length > 0
          ? 'Action Required'
          : 'All skills aligned',
    },
  ];

  const steps = [
    { name: 'Process Resume', href: '/candidates/upload-resume', icon: Upload },
    { name: 'Find Best Job Match', href: '/jobs/upload-jd', icon: Target },
    { name: 'Skill Gap Analysis', href: '/skill-gap', icon: TrendingUp },
    { name: 'Generate Assessment', href: '/assessments/create', icon: CheckCircle },
    { name: 'Start Interview', href: '/interviews/questions', icon: Send },
    { name: 'View Evaluation Results', href: '/interviews/results', icon: FileText },
  ];

  return (
    <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-foreground">
          Candidate Dashboard
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Manage your candidate evaluation process efficiently with AI insights.
        </p>
      </div>

      {/* Progress Section */}
     <Card className="border border-muted/40 bg-gradient-to-r from-primary/5 via-primary/10 to-transparent">
  <CardHeader className="pb-2">
    <CardTitle className="flex items-center gap-2 text-lg font-semibold">
      <Clock className="h-5 w-5 text-primary" />
      Current Evaluation Progress
    </CardTitle>
  </CardHeader>
  <CardContent className="space-y-3">
    <div className="flex items-center justify-between text-sm">
      <span className="font-medium text-muted-foreground">{getProgressPhase()}</span>
      <span className="font-semibold text-primary">{progressValue}%</span>
    </div>

    {/* keep Progress component as-is but ensure it receives the robust value */}
    <div role="progressbar" aria-valuenow={progressValue} aria-valuemin={0} aria-valuemax={100}>
      <Progress value={progressValue} className="h-2" />
    </div>

    {currentSession.threadId && (
      <p className="text-xs text-muted-foreground">
        Session ID: {currentSession.threadId.substring(0, 8)}...
      </p>
    )}
  </CardContent>
</Card>


      {/* Stats Section */}
      <div className="grid gap-4 md:grid-cols-3">
        {stats.map((stat) => {
          const Icon = stat.icon;
          return (
            <Card key={stat.name} className="hover:shadow-lg transition-all border-muted/40">
              <CardContent className="p-5 flex flex-col gap-1">
                <div className="flex justify-between items-center">
                  <p className="text-sm font-medium text-muted-foreground">{stat.name}</p>
                  <Icon className="h-4 w-4 text-muted-foreground" />
                </div>
                <p className={`text-2xl font-bold ${stat.color}`}>{stat.value}</p>
                <p className="text-xs text-muted-foreground">{stat.change}</p>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Step-by-step Flow */}
      <Card className="shadow-sm border border-muted/40 transition-all hover:shadow-md">
        <CardContent className="p-6 space-y-5">
          <div>
            <h2 className="text-xl font-semibold mb-2">Evaluation Workflow</h2>
            <p className="text-sm text-muted-foreground">
              Complete each step below to finish the candidate evaluation process.
            </p>
          </div>

          <div className="space-y-3">
            {steps.map((step, index) => {
              const Icon = step.icon;
              const isUploadStep = index === 0;
              const hasResume = currentSession.state?.candidate_skills?.length > 0;

              const isCompleted =
                (isUploadStep && hasResume) ||
                (index === 1 && currentSession.state?.jd_text) ||
                (index === 2 && currentSession.state?.skill_resources) ||
                (index === 3 && currentSession.state?.mcqs?.length > 0) ||
                (index === 4 && currentSession.state?.interview_questions?.length > 0) ||
                (index === 5 && currentSession.state?.feedback);

              const isDisabled = !isUploadStep && !hasResume;

              return (
                <div
                  key={step.name}
                  className={`flex items-center gap-4 p-4 rounded-lg border transition-all ${
                    isCompleted
                      ? 'bg-primary/5 border-primary/20'
                      : 'bg-card border-muted/30'
                  }`}
                >
                  <div
                    className={`w-9 h-9 rounded-full flex items-center justify-center font-semibold text-sm ${
                      isCompleted
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-muted text-muted-foreground'
                    }`}
                  >
                    {index + 1}
                  </div>
                  <Icon
                    className={`h-5 w-5 ${
                      isCompleted ? 'text-primary' : 'text-muted-foreground'
                    }`}
                  />
                  <div className="flex-1">
                    <h3 className="font-medium text-foreground">{step.name}</h3>
                    <p className="text-xs text-muted-foreground">
                      {index === 0 && 'Upload and analyze the candidate resume.'}
                      {index === 1 && 'Match resume with job descriptions to find the best fit.'}
                      {index === 2 && 'Identify missing skills and suggest learning paths.'}
                      {index === 3 && 'Create and take skill-based assessments.'}
                      {index === 4 && 'Generate personalized interview questions.'}
                      {index === 5 && 'Review feedback, score, and final summary.'}
                    </p>
                  </div>
                  {isDisabled ? (
                    <Button variant="outline" size="sm" disabled>
                      View
                    </Button>
                  ) : (
                    <Link to={step.href}>
                      <Button
                        variant={isUploadStep ? 'default' : 'outline'}
                        size="sm"
                        className="flex items-center gap-1"
                      >
                        {isUploadStep ? 'Start' : 'View'}
                        <ChevronRight className="h-3 w-3" />
                      </Button>
                    </Link>
                  )}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Recent Activity */}
      {currentSession.state && (
        <Card className="shadow-sm border border-muted/40 transition-all hover:shadow-md">
          <CardHeader>
            <CardTitle className="text-lg font-semibold">Recent Activity</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            {currentSession.state.candidate_skills.length > 0 && (
              <p>✅ Resume processed — {currentSession.state.candidate_skills.length} skills identified</p>
            )}
            {currentSession.state.jd_skills.length > 0 && (
              <p>🎯 Job analysis completed — {currentSession.state.jd_skills.length} skills matched</p>
            )}
            {currentSession.state.match_score > 0 && (
              <p>📊 Match score calculated — {Math.round(currentSession.state.match_score * 100)}% fit</p>
            )}
            {currentSession.state.interview_questions?.length > 0 && (
              <p>🗣️ Interview questions generated — {currentSession.state.interview_questions.length}</p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
