import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { 
  Target, 
  CheckCircle, 
  X,
  User,
  Briefcase,
  TrendingUp,
  AlertTriangle
} from 'lucide-react';
import { apiService, CandidateState } from '@/services/api';
import { useToast } from '@/hooks/use-toast';
import { useNavigate } from 'react-router-dom';

export default function Matching() {
  const [currentSession, setCurrentSession] = useState<{
    threadId?: string;
    state?: CandidateState;
  }>({});
  const [isMatching, setIsMatching] = useState(false);
  const [matchResults, setMatchResults] = useState<CandidateState | null>(null);
  
  const { toast } = useToast();
  const navigate = useNavigate();

  useEffect(() => {
    loadSessionFromStorage();
  }, []);

  const loadSessionFromStorage = () => {
    const stored = localStorage.getItem('talentai-session');
    if (stored) {
      try {
        const session = JSON.parse(stored);
        setCurrentSession(session);
        
        if (!session.state?.candidate_skills?.length) {
          toast({
            title: "Resume Required",
            description: "Please upload a resume first",
            variant: "destructive",
          });
          navigate('/candidates/upload-resume');
          return;
        }
        
        if (!session.state?.jd_skills?.length) {
          toast({
            title: "Job Description Required",
            description: "Please upload a job description first",
            variant: "destructive",
          });
          navigate('/jobs/upload-jd');
          return;
        }

        // If we already have match results, show them
        if (session.state?.match_score > 0) {
          setMatchResults(session.state);
        }
      } catch (error) {
        console.error('Failed to load session:', error);
        navigate('/candidates/upload-resume');
      }
    } else {
      navigate('/candidates/upload-resume');
    }
  };

  const runMatching = async () => {
    if (!currentSession.threadId || !currentSession.state) {
      toast({
        title: "Missing Information",
        description: "Please ensure you have uploaded both resume and job description",
        variant: "destructive",
      });
      return;
    }
    
    setIsMatching(true);
    
    try {
      const response = await apiService.matchResumeWithJD({
        state: currentSession.state,
        thread_id: currentSession.threadId
      });
      
      setMatchResults(response.state);
      
      // Update session in localStorage
      const updatedSession = {
        threadId: response.thread_id,
        state: response.state,
        progress: 60
      };
      localStorage.setItem('talentai-session', JSON.stringify(updatedSession));
      setCurrentSession(updatedSession);
      
      toast({
        title: "Matching Complete",
        description: `Match score: ${Math.round(response.match_score * 100)}%`,
      });
      
    } catch (error) {
      toast({
        title: "Matching Failed",
        description: "Failed to run candidate matching. Please try again.",
        variant: "destructive",
      });
    } finally {
      setIsMatching(false);
    }
  };

  const continueToSkillGap = () => {
    navigate('/skill-gap');
  };

  const getMatchColor = (score: number) => {
    if (score >= 0.8) return 'text-green-600';
    if (score >= 0.6) return 'text-yellow-600';
    return 'text-red-600';
  };

  const getMatchLabel = (score: number) => {
    if (score >= 0.8) return 'Excellent Match';
    if (score >= 0.6) return 'Good Match';
    if (score >= 0.4) return 'Fair Match';
    return 'Poor Match';
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Candidate-Role Matching</h1>
        <p className="text-muted-foreground">
          Compare candidate skills with job requirements to calculate compatibility score
        </p>
      </div>

      {/* Session Overview */}
      {currentSession.state && (
        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <User className="h-4 w-4" />
                Candidate Skills
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground mb-2">
                  {currentSession.state.candidate_skills.length} skills identified
                </p>
                <div className="flex flex-wrap gap-1">
                  {currentSession.state.candidate_skills.slice(0, 10).map((skill, index) => (
                    <Badge key={index} variant="secondary" className="text-xs">
                      {skill}
                    </Badge>
                  ))}
                  {currentSession.state.candidate_skills.length > 10 && (
                    <Badge variant="outline" className="text-xs">
                      +{currentSession.state.candidate_skills.length - 10} more
                    </Badge>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <Briefcase className="h-4 w-4" />
                Job Requirements
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground mb-2">
                  {currentSession.state.jd_skills.length} skills required
                </p>
                <div className="flex flex-wrap gap-1">
                  {currentSession.state.jd_skills.slice(0, 10).map((skill, index) => (
                    <Badge key={index} variant="secondary" className="text-xs">
                      {skill}
                    </Badge>
                  ))}
                  {currentSession.state.jd_skills.length > 10 && (
                    <Badge variant="outline" className="text-xs">
                      +{currentSession.state.jd_skills.length - 10} more
                    </Badge>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Matching Results or Action */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Target className="h-5 w-5" />
            Matching Analysis
          </CardTitle>
        </CardHeader>
        <CardContent>
          {!matchResults || matchResults.match_score === 0 ? (
            <div className="text-center py-8 space-y-4">
              <Target className="h-16 w-16 mx-auto text-muted-foreground" />
              <div>
                <h3 className="text-lg font-semibold mb-2">Ready to Run Matching</h3>
                <p className="text-muted-foreground mb-6">
                  Analyze candidate skills against job requirements using AI-powered matching algorithms
                </p>
                <Button 
                  onClick={runMatching} 
                  disabled={isMatching}
                  size="lg"
                >
                  {isMatching ? 'Running Analysis...' : 'Run Candidate Matching'}
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Overall Match Score */}
              <div className="text-center py-6 border-b">
                <div className="space-y-2">
                  <p className="text-sm text-muted-foreground">Overall Match Score</p>
                  <div className={`text-4xl font-bold ${getMatchColor(matchResults.match_score)}`}>
                    {Math.round(matchResults.match_score * 100)}%
                  </div>
                  <p className={`text-sm font-medium ${getMatchColor(matchResults.match_score)}`}>
                    {getMatchLabel(matchResults.match_score)}
                  </p>
                </div>
              </div>

              {/* Detailed Scores */}
              <div className="grid gap-4 md:grid-cols-3">
                <Card>
                  <CardContent className="p-4 text-center">
                    <p className="text-sm text-muted-foreground mb-1">TF-IDF Score</p>
                    <p className="text-xl font-semibold">
                      {Math.round(matchResults.tfidf_score * 100)}%
                    </p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-4 text-center">
                    <p className="text-sm text-muted-foreground mb-1">Semantic Score</p>
                    <p className="text-xl font-semibold">
                      {Math.round(matchResults.embedding_score * 100)}%
                    </p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-4 text-center">
                    <p className="text-sm text-muted-foreground mb-1">Keyword Score</p>
                    <p className="text-xl font-semibold">
                      {Math.round(matchResults.bow_score * 100)}%
                    </p>
                  </CardContent>
                </Card>
              </div>

              {/* Matched Skills */}
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <CheckCircle className="h-4 w-4 text-success" />
                  <h3 className="font-semibold">Matched Skills</h3>
                  <Badge variant="secondary">{matchResults.matched_skills.length}</Badge>
                </div>
                <div className="flex flex-wrap gap-2">
                  {matchResults.matched_skills.map((skill, index) => (
                    <Badge key={index} variant="default" className="bg-success/10 text-success border-success/20">
                      <CheckCircle className="h-3 w-3 mr-1" />
                      {skill}
                    </Badge>
                  ))}
                </div>
              </div>

              {/* Missing Skills */}
              {matchResults.missing_skills.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <AlertTriangle className="h-4 w-4 text-warning" />
                    <h3 className="font-semibold">Missing Skills</h3>
                    <Badge variant="secondary">{matchResults.missing_skills.length}</Badge>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {matchResults.missing_skills.map((skill, index) => (
                      <Badge key={index} variant="outline" className="text-warning border-warning/30">
                        <X className="h-3 w-3 mr-1" />
                        {skill}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              {/* Next Steps */}
              <div className="pt-4 border-t">
                <Button onClick={continueToSkillGap} className="w-full">
                  <TrendingUp className="h-4 w-4 mr-2" />
                  Continue to Skill Gap Analysis
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}