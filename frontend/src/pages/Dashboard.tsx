import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { 
  Users, 
  FileText, 
  Target, 
  TrendingUp, 
  Upload, 
  CheckCircle,
  AlertCircle,
  Clock
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { apiService, CandidateState } from '@/services/api';
import { useToast } from '@/hooks/use-toast';

export default function Dashboard() {
  const [currentSession, setCurrentSession] = useState<{
    threadId?: string;
    state?: CandidateState;
    progress: number;
  }>({ progress: 0 });
  
  const { toast } = useToast();

  useEffect(() => {
    loadSessionFromStorage();
  }, []);

  const loadSessionFromStorage = () => {
    const stored = localStorage.getItem('talentai-session');
    if (stored) {
      try {
        const session = JSON.parse(stored);
        setCurrentSession(session);
      } catch (error) {
        console.error('Failed to load session:', error);
      }
    }
  };

  const getProgressPhase = () => {
    if (!currentSession.state) return 'Start by uploading a resume';
    if (!currentSession.state.candidate_skills.length) return 'Resume processing...';
    if (!currentSession.state.jd_text) return 'Upload job description';
    if (!currentSession.state.jd_skills.length) return 'Job description processing...';
    if (currentSession.state.match_score === 0) return 'Run candidate matching';
    if (!currentSession.state.skill_resources || Object.keys(currentSession.state.skill_resources).length === 0) return 'Analyze skill gaps';
    if (!currentSession.state.mcqs.length) return 'Generate assessment';
    if (!currentSession.state.interview_questions.length) return 'Generate interview questions';
    return 'Complete workflow ready for evaluation';
  };

  const calculateProgress = () => {
    if (!currentSession.state) return 0;
    
    let progress = 0;
    if (currentSession.state.candidate_skills.length > 0) progress += 20;
    if (currentSession.state.jd_skills.length > 0) progress += 20;
    if (currentSession.state.match_score > 0) progress += 20;
    if (currentSession.state.skill_resources && Object.keys(currentSession.state.skill_resources).length > 0) progress += 15;
    if (currentSession.state.mcqs.length > 0) progress += 15;
    if (currentSession.state.interview_questions.length > 0) progress += 10;
    
    return Math.min(progress, 100);
  };

  const quickActions = [
    {
      title: 'Upload Resume',
      description: 'Start the process by uploading a candidate resume',
      href: '/candidates/upload-resume',
      icon: Upload,
      color: 'bg-gradient-primary',
    },
    {
      title: 'Upload Job Description',
      description: 'Define role requirements and skills needed',
      href: '/jobs/upload-jd',
      icon: FileText,
      color: 'bg-gradient-secondary',
    },
    {
      title: 'View Matching',
      description: 'Compare candidate skills with job requirements',
      href: '/matching',
      icon: Target,
      color: 'bg-gradient-hero',
    },
    {
      title: 'Skill Gap Analysis',
      description: 'Identify missing skills and learning resources',
      href: '/skill-gap',
      icon: TrendingUp,
      color: 'bg-gradient-primary',
    },
  ];

  const stats = [
    {
      name: 'Candidates Processed',
      value: currentSession.state ? 1 : 0,
      icon: Users,
      change: currentSession.state ? '+1' : '0',
    },
    {
      name: 'Match Score',
      value: currentSession.state ? `${Math.round(currentSession.state.match_score * 100)}%` : '0%',
      icon: Target,
      change: currentSession.state && currentSession.state.match_score > 0.7 ? 'High' : currentSession.state && currentSession.state.match_score > 0.4 ? 'Medium' : 'Low',
    },
    {
      name: 'Skills Identified',
      value: currentSession.state ? currentSession.state.candidate_skills.length : 0,
      icon: CheckCircle,
      change: currentSession.state ? `${currentSession.state.matched_skills.length} matched` : '0',
    },
    {
      name: 'Missing Skills',
      value: currentSession.state ? currentSession.state.missing_skills.length : 0,
      icon: AlertCircle,
      change: currentSession.state && currentSession.state.missing_skills.length > 0 ? 'Action needed' : 'All good',
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Dashboard</h1>
          <p className="text-muted-foreground">
            AI-powered talent acquisition and candidate evaluation platform
          </p>
        </div>
      </div>

      {/* Current Session Progress */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Clock className="h-5 w-5" />
            Current Session Progress
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">{getProgressPhase()}</span>
            <span className="font-medium">{calculateProgress()}%</span>
          </div>
          <Progress value={calculateProgress()} className="h-2" />
          {currentSession.threadId && (
            <p className="text-xs text-muted-foreground">
              Session ID: {currentSession.threadId.substring(0, 8)}...
            </p>
          )}
        </CardContent>
      </Card>

      {/* Stats Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => {
          const Icon = stat.icon;
          return (
            <Card key={stat.name}>
              <CardContent className="p-6">
                <div className="flex items-center justify-between space-y-0 pb-2">
                  <p className="text-sm font-medium text-muted-foreground">
                    {stat.name}
                  </p>
                  <Icon className="h-4 w-4 text-muted-foreground" />
                </div>
                <div className="space-y-1">
                  <p className="text-2xl font-bold">{stat.value}</p>
                  <p className="text-xs text-muted-foreground">
                    {stat.change}
                  </p>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Sequential Process Flow */}
      <Card className="p-6">
        <h2 className="text-xl font-semibold mb-4">Talent Acquisition Process</h2>
        <p className="text-muted-foreground mb-6">
          Follow these sequential steps to complete a comprehensive candidate evaluation.
        </p>
        
        <div className="space-y-4">
          {[
            { name: 'Upload Resume', href: '/candidates/upload-resume', icon: Upload, step: 0 },
            { name: 'Upload Job Description', href: '/jobs/upload-jd', icon: FileText, step: 1 },
            { name: 'Matching', href: '/matching', icon: Target, step: 2 },
            { name: 'Skill Gap Analysis', href: '/skill-gap', icon: TrendingUp, step: 3 },
            { name: 'Create Assessment', href: '/assessments/create', icon: CheckCircle, step: 4 },
            { name: 'Interview Questions', href: '/interviews/questions', icon: AlertCircle, step: 5 },
          ].map((step, index) => {
            const Icon = step.icon;
            const isCompleted = false; // You can add state tracking here
            
            return (
              <div key={step.name} className="flex items-center gap-4 p-4 rounded-lg border bg-card">
                <div className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold ${
                  isCompleted ? 'bg-success text-success-foreground' : 'bg-muted text-muted-foreground'
                }`}>
                  {index + 1}
                </div>
                <Icon className="h-5 w-5 text-muted-foreground" />
                <div className="flex-1">
                  <h3 className="font-medium">{step.name}</h3>
                  <p className="text-sm text-muted-foreground">
                    {index === 0 && "Upload and analyze candidate resume"}
                    {index === 1 && "Upload and process job description"}
                    {index === 2 && "Compare candidate skills with job requirements"}
                    {index === 3 && "Identify missing skills and learning resources"}
                    {index === 4 && "Generate skill-based assessments"}
                    {index === 5 && "Create interview questions and evaluate"}
                  </p>
                </div>
                <Link to={step.href}>
                  <Button variant={index === 0 ? "default" : "outline"} size="sm">
                    {index === 0 ? "Start" : "View"}
                  </Button>
                </Link>
              </div>
            );
          })}
        </div>
      </Card>

      {/* Recent Activity */}
      {currentSession.state && (
        <Card>
          <CardHeader>
            <CardTitle>Recent Activity</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {currentSession.state.candidate_skills.length > 0 && (
                <div className="flex items-center gap-3">
                  <CheckCircle className="h-4 w-4 text-success" />
                  <span className="text-sm">Resume processed - {currentSession.state.candidate_skills.length} skills identified</span>
                </div>
              )}
              {currentSession.state.jd_skills.length > 0 && (
                <div className="flex items-center gap-3">
                  <CheckCircle className="h-4 w-4 text-success" />
                  <span className="text-sm">Job description analyzed - {currentSession.state.jd_skills.length} required skills found</span>
                </div>
              )}
              {currentSession.state.match_score > 0 && (
                <div className="flex items-center gap-3">
                  <CheckCircle className="h-4 w-4 text-success" />
                  <span className="text-sm">Candidate match completed - {Math.round(currentSession.state.match_score * 100)}% compatibility</span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}