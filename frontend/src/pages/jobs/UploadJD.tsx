import { useState, useEffect, useCallback } from 'react';
import { 
  Card, CardContent, CardHeader, CardTitle, CardDescription 
} from '@/components/ui/card';
import { 
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription 
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { 
  FileText, 
  CheckCircle2, 
  Briefcase,
  Users,
  Target,
  Search,
  Zap,
  Percent,
  AlertTriangle,
  Calendar,
  Building2,
  Eye
} from 'lucide-react';
import { apiService, CandidateState } from '@/services/api';
import { useToast } from '@/hooks/use-toast';
import { useNavigate } from 'react-router-dom';

type JDListItem = { id: string; title: string; text?: string; company?: string; date?: string };

interface ProcessedJDState extends CandidateState {
  bestMatchTitle?: string;
  company?: string;
  date?: string;
  jd_text?: string;
}

export default function UploadJD() {
  const [availableJDs, setAvailableJDs] = useState<JDListItem[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [currentSession, setCurrentSession] = useState<{ threadId?: string; state?: CandidateState }>({});
  const [processedJD, setProcessedJD] = useState<ProcessedJDState | null>(null);
  const [selectedJDText, setSelectedJDText] = useState<string | null>(null);

  const { toast } = useToast();
  const navigate = useNavigate();

  const loadData = useCallback(() => {
    const stored = localStorage.getItem('talentai-session');
    if (stored) {
      try {
        const session = JSON.parse(stored);
        setCurrentSession(session);
        if (!session.state?.candidate_skills?.length) {
          toast({
            title: "Resume Required",
            description: "Please upload a resume first.",
            variant: "destructive",
          });
          navigate('/candidates/upload-resume');
          return;
        }
      } catch {
        navigate('/candidates/upload-resume');
      }
    } else {
      navigate('/candidates/upload-resume');
    }

    apiService.getAvailableJDs()
      .then((data) => setAvailableJDs(data.map(jd => ({ ...jd, id: jd.id.toString() }))))
      .catch(() => {
        toast({
          title: "JD Fetch Failed",
          description: "Could not retrieve job descriptions.",
          variant: "destructive",
        });
      });
  }, [navigate, toast]);

  useEffect(() => { loadData(); }, [loadData]);

  const processJD = async () => {
    if (!currentSession.threadId || !currentSession.state) {
      toast({
        title: "Missing Info",
        description: "Please ensure you have uploaded a resume.",
        variant: "destructive",
      });
      return;
    }

    setIsProcessing(true);
    setProgress(10);

    try {
      const response = await apiService.matchAllJDs({
        state: currentSession.state,
        thread_id: currentSession.threadId,
      });

      setProgress(100);

      setProcessedJD({
        ...response.state,
        bestMatchTitle: response.best_match_title,
        company: response.company,
        date: response.date,
        jd_text: response.jd_text, // full JD from backend
      });

      const updatedSession = {
        threadId: response.thread_id,
        state: response.state,
        progress: 40,
      };
      localStorage.setItem('talentai-session', JSON.stringify(updatedSession));
      setCurrentSession(updatedSession);

      toast({
        title: "Best Match Found",
        description: `${response.best_match_title} (${Math.round(response.match_score * 100)}%)`,
      });

    } catch {
      toast({
        title: "Matching Failed",
        description: "Unable to match resume with JDs.",
        variant: "destructive",
      });
    } finally {
      setIsProcessing(false);
    }
  };

  const continueToMatching = () => navigate('/skill-gap');

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Find Best Job Match</h1>
        <p className="text-muted-foreground">
          Automatically match your resume with the best available job descriptions.
        </p>
      </div>

      {/* Candidate Overview */}
      {currentSession.state && (
        <Card className="border-primary/20 bg-primary/5">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-2">
              <Users className="h-4 w-4 text-primary" />
              <span className="font-medium">Current Candidate</span>
            </div>
            <p className="text-sm text-muted-foreground mb-2">
              {currentSession.state.candidate_skills.length} skills identified
            </p>
            <div className="flex flex-wrap gap-2">
              {currentSession.state.candidate_skills.slice(0, 10).map((skill, index) => (
                <Badge key={index} variant="secondary" className="text-xs">{skill}</Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Main Grid */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Matching Section */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Search className="h-5 w-5" />
              Start Automated Matching
            </CardTitle>
            <CardDescription>
              Run the candidate's resume against all job descriptions.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {availableJDs.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {availableJDs.map((jd) => (
                  <Badge key={jd.id} variant="default" className="bg-muted text-muted-foreground">
                    {jd.title}
                  </Badge>
                ))}
              </div>
            ) : (
              <div className="text-center py-4 text-muted-foreground">
                No job descriptions found.
              </div>
            )}

            {isProcessing && (
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span>Matching in progress...</span>
                  <span>{progress}%</span>
                </div>
                <Progress value={progress} />
              </div>
            )}

            <Button 
              onClick={processJD} 
              disabled={isProcessing || availableJDs.length === 0}
              className="w-full"
            >
              <Zap className="h-4 w-4 mr-2" />
              {isProcessing ? 'Processing...' : `Find Best Match (${availableJDs.length})`}
            </Button>
          </CardContent>
        </Card>

        {/* Result Section */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Briefcase className="h-5 w-5" />
              Best Match Analysis
            </CardTitle>
          </CardHeader>
          <CardContent>
            {!processedJD ? (
              <div className="text-center py-8 text-muted-foreground">
                <FileText className="h-12 w-12 mx-auto mb-4" />
                Run the matching process to find your best-fit job.
              </div>
            ) : (
              <div className="space-y-6">
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <Target className="h-4 w-4 text-success" />
                    <h3 className="font-semibold text-lg">Best Match Found:</h3>
                  </div>
                  <p className="text-xl font-bold text-primary">
                    {processedJD.bestMatchTitle || 'N/A'}
                  </p>

                  <p className="text-sm text-muted-foreground">
                    Match Score: <Percent className="inline h-3 w-3 align-text-bottom mr-1" />
                    <span className="font-semibold text-md text-foreground">
                      {Math.round(processedJD.match_score * 100)}%
                    </span>
                  </p>

                  {(processedJD.company || processedJD.date) && (
                    <div className="flex items-center gap-3 mt-2 text-sm text-muted-foreground">
                      {processedJD.company && (
                        <div className="flex items-center gap-1">
                          <Building2 className="h-4 w-4 text-blue-600" />
                          <span>{processedJD.company}</span>
                        </div>
                      )}
                      {processedJD.date && (
                        <div className="flex items-center gap-1">
                          <Calendar className="h-4 w-4 text-indigo-500" />
                          <span>
                            Posted{' '}
                            {(() => {
                              const postedDate = new Date(processedJD.date);
                              const diffDays = Math.floor(
                                (Date.now() - postedDate.getTime()) / (1000 * 60 * 60 * 24)
                              );
                              return diffDays === 0
                                ? 'today'
                                : diffDays === 1
                                ? '1 day ago'
                                : `${diffDays} days ago`;
                            })()}
                          </span>
                        </div>
                      )}
                    </div>
                  )}

                  {/* View Full JD Button */}
                  {processedJD.jd_text && (
                    <Button 
                      variant="outline" 
                      size="sm" 
                      className="mt-4"
                      onClick={() => setSelectedJDText(processedJD.jd_text!)}
                    >
                       View Full JD
                    </Button>
                  )}
                </div>

                {/* Skills */}
                {processedJD.matched_skills?.length > 0 && (
                  <div>
                    <div className="flex items-center gap-2 mb-3">
                      <CheckCircle2 className="h-4 w-4 text-green-600" />
                      <h3 className="font-semibold">Matched Skills</h3>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {processedJD.matched_skills.map((skill, index) => (
                        <Badge key={index} variant="outline" className="border-green-600 text-green-700">
                          {skill}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}

                {processedJD.missing_skills?.length > 0 && (
                  <div>
                    <div className="flex items-center gap-2 mb-3">
                      <AlertTriangle className="h-4 w-4 text-yellow-600" />
                      <h3 className="font-semibold">Missing Skills</h3>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {processedJD.missing_skills.map((skill, index) => (
                        <Badge key={index} variant="outline" className="border-yellow-600 text-yellow-700">
                          {skill}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}

                <div className="pt-4 border-t">
                  <Button onClick={continueToMatching} className="w-full">
                    <Target className="h-4 w-4 mr-2" /> Continue to Skill Gap Analysis
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* JD Modal */}
      <Dialog open={!!selectedJDText} onOpenChange={() => setSelectedJDText(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="text-lg font-semibold">
              {processedJD?.bestMatchTitle}
            </DialogTitle>
            <DialogDescription>
              <div className="flex items-center justify-between mt-1 text-sm text-muted-foreground">
                <span>{processedJD?.company}</span>
                {processedJD?.date && (
                  <span>
                    Posted {new Date(processedJD.date).toLocaleDateString()}
                  </span>
                )}
              </div>
            </DialogDescription>
          </DialogHeader>
          <div className="mt-4 max-h-[400px] overflow-y-auto pr-2 text-sm whitespace-pre-wrap leading-relaxed">
            {selectedJDText}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
