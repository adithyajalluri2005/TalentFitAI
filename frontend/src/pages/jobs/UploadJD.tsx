import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { 
  FileText, 
  CheckCircle, 
  Briefcase,
  Star,
  Users,
  Target
} from 'lucide-react';
import { apiService, CandidateState } from '@/services/api';
import { useToast } from '@/hooks/use-toast';
import { useNavigate } from 'react-router-dom';

export default function UploadJD() {
  const [jdText, setJdText] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [currentSession, setCurrentSession] = useState<{
    threadId?: string;
    state?: CandidateState;
  }>({});
  const [processedJD, setProcessedJD] = useState<CandidateState | null>(null);
  
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
            description: "Please upload a resume first before adding job description",
            variant: "destructive",
          });
          navigate('/candidates/upload-resume');
        }
      } catch (error) {
        console.error('Failed to load session:', error);
        navigate('/candidates/upload-resume');
      }
    } else {
      navigate('/candidates/upload-resume');
    }
  };

  const processJD = async () => {
    if (!jdText.trim() || !currentSession.threadId || !currentSession.state) {
      toast({
        title: "Missing Information",
        description: "Please ensure you have uploaded a resume first",
        variant: "destructive",
      });
      return;
    }
    
    setIsProcessing(true);
    setProgress(10);
    
    try {
      const response = await apiService.uploadJobDescription({
        state: { ...currentSession.state, jd_text: jdText },
        thread_id: currentSession.threadId
      });
      setProgress(100);
      
      setProcessedJD(response.state);
      
      // Update session in localStorage
      const updatedSession = {
        threadId: response.thread_id,
        state: response.state,
        progress: 40
      };
      localStorage.setItem('talentai-session', JSON.stringify(updatedSession));
      setCurrentSession(updatedSession);
      
      toast({
        title: "Job Description Processed",
        description: `Identified ${response.jd_skills.length} required skills`,
      });
      
    } catch (error) {
      toast({
        title: "Processing Failed",
        description: "Failed to process job description. Please try again.",
        variant: "destructive",
      });
    } finally {
      setIsProcessing(false);
    }
  };

  const continueToMatching = () => {
    navigate('/matching');
  };

  const sampleJD = `Senior Software Engineer - Full Stack Development

We are seeking an experienced Senior Software Engineer to join our dynamic team. The ideal candidate will have strong expertise in both frontend and backend development.

Key Responsibilities:
- Design and develop scalable web applications using React, Node.js, and modern frameworks
- Collaborate with cross-functional teams to define and implement new features
- Write clean, maintainable, and well-documented code
- Optimize applications for maximum speed and scalability
- Mentor junior developers and participate in code reviews

Required Skills:
- 5+ years of experience in software development
- Proficiency in JavaScript, TypeScript, Python
- Experience with React, Node.js, Express.js
- Strong knowledge of databases (PostgreSQL, MongoDB)
- Familiarity with cloud platforms (AWS, Azure)
- Experience with Git, CI/CD pipelines
- Strong problem-solving and communication skills

Preferred:
- Experience with Docker and Kubernetes
- Knowledge of microservices architecture
- Familiarity with machine learning concepts`;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Upload Job Description</h1>
        <p className="text-muted-foreground">
          Add job requirements to compare against candidate skills and identify gaps
        </p>
      </div>

      {/* Current Session Info */}
      {currentSession.state && (
        <Card className="border-primary/20 bg-primary/5">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-2">
              <Users className="h-4 w-4 text-primary" />
              <span className="font-medium">Current Candidate</span>
            </div>
            <p className="text-sm text-muted-foreground mb-2">
              Resume processed with {currentSession.state.candidate_skills.length} skills identified
            </p>
            <div className="flex flex-wrap gap-2">
              {currentSession.state.candidate_skills.slice(0, 8).map((skill, index) => (
                <Badge key={index} variant="secondary" className="text-xs">
                  {skill}
                </Badge>
              ))}
              {currentSession.state.candidate_skills.length > 8 && (
                <Badge variant="secondary" className="text-xs">
                  +{currentSession.state.candidate_skills.length - 8} more
                </Badge>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Input Section */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Job Description
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Textarea
                placeholder="Paste the job description here or use the sample below..."
                value={jdText}
                onChange={(e) => setJdText(e.target.value)}
                className="min-h-[300px] resize-none"
              />
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setJdText(sampleJD)}
                  disabled={isProcessing}
                >
                  Use Sample JD
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setJdText('')}
                  disabled={isProcessing}
                >
                  Clear
                </Button>
              </div>
            </div>

            {isProcessing && (
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span>Processing job description...</span>
                  <span>{progress}%</span>
                </div>
                <Progress value={progress} />
              </div>
            )}

            <Button 
              onClick={processJD} 
              disabled={!jdText.trim() || isProcessing}
              className="w-full"
            >
              {isProcessing ? 'Processing...' : 'Process Job Description'}
            </Button>
          </CardContent>
        </Card>

        {/* Results Section */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Briefcase className="h-5 w-5" />
              Required Skills Analysis
            </CardTitle>
          </CardHeader>
          <CardContent>
            {!processedJD ? (
              <div className="text-center py-8">
                <FileText className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
                <p className="text-muted-foreground">
                  Process a job description to see required skills
                </p>
              </div>
            ) : (
              <div className="space-y-6">
                {/* Required Skills */}
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <Star className="h-4 w-4" />
                    <h3 className="font-semibold">Required Skills</h3>
                    <Badge variant="secondary">{processedJD.jd_skills.length}</Badge>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {processedJD.jd_skills.slice(0, 15).map((skill, index) => (
                      <Badge key={index} variant="outline">
                        {skill}
                      </Badge>
                    ))}
                    {processedJD.jd_skills.length > 15 && (
                      <Badge variant="secondary">
                        +{processedJD.jd_skills.length - 15} more
                      </Badge>
                    )}
                  </div>
                </div>

                {/* Experience Level */}
                {processedJD.jd_experience && (
                  <div>
                    <div className="flex items-center gap-2 mb-3">
                      <Briefcase className="h-4 w-4" />
                      <h3 className="font-semibold">Experience Level</h3>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      {processedJD.jd_experience}
                    </p>
                  </div>
                )}

                {/* Next Steps */}
                <div className="pt-4 border-t">
                  <div className="flex items-center gap-2 mb-3">
                    <CheckCircle className="h-4 w-4 text-success" />
                    <span className="text-sm font-medium">Job description processed successfully</span>
                  </div>
                  <Button onClick={continueToMatching} className="w-full">
                    <Target className="h-4 w-4 mr-2" />
                    Continue to Candidate Matching
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}