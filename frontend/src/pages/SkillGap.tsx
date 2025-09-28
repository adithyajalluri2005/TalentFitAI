import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { 
  TrendingUp, 
  ExternalLink,
  Book,
  Video,
  Users,
  ClipboardList,
  Star,
  AlertCircle
} from 'lucide-react';
import { apiService, CandidateState } from '@/services/api';
import { useToast } from '@/hooks/use-toast';
import { useNavigate } from 'react-router-dom';

export default function SkillGap() {
  const [currentSession, setCurrentSession] = useState<{
    threadId?: string;
    state?: CandidateState;
  }>({});
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [skillGapData, setSkillGapData] = useState<CandidateState | null>(null);
  
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
        
        if (!session.state?.missing_skills?.length && !session.state?.matched_skills?.length) {
          toast({
            title: "Matching Required",
            description: "Please complete candidate matching first",
            variant: "destructive",
          });
          navigate('/matching');
          return;
        }

        // If we already have skill gap data, show it
        if (session.state?.skill_resources && Object.keys(session.state.skill_resources).length > 0) {
          setSkillGapData(session.state);
        }
      } catch (error) {
        console.error('Failed to load session:', error);
        navigate('/matching');
      }
    } else {
      navigate('/matching');
    }
  };

  const runSkillGapAnalysis = async () => {
    if (!currentSession.threadId || !currentSession.state) {
      toast({
        title: "Missing Information",
        description: "Please complete matching first",
        variant: "destructive",
      });
      return;
    }
    
    setIsAnalyzing(true);
    
    try {
      const response = await apiService.analyzeSkillGap({
        state: currentSession.state,
        thread_id: currentSession.threadId
      });
      
      setSkillGapData(response.state);
      
      // Update session in localStorage
      const updatedSession = {
        threadId: response.thread_id,
        state: response.state,
        progress: 75
      };
      localStorage.setItem('talentai-session', JSON.stringify(updatedSession));
      setCurrentSession(updatedSession);
      
      toast({
        title: "Analysis Complete",
        description: `Found learning resources for ${response.priority_skills.length} priority skills`,
      });
      
    } catch (error) {
      toast({
        title: "Analysis Failed",
        description: "Failed to analyze skill gaps. Please try again.",
        variant: "destructive",
      });
    } finally {
      setIsAnalyzing(false);
    }
  };

  const continueToAssessment = () => {
    navigate('/assessments/create');
  };

  const getResourceIcon = (type: string) => {
    switch (type.toLowerCase()) {
      case 'course':
        return Book;
      case 'video':
        return Video;
      case 'tutorial':
        return Users;
      default:
        return Book;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Skill Gap Analysis</h1>
        <p className="text-muted-foreground">
          Identify missing skills and get personalized learning recommendations to bridge the gap
        </p>
      </div>

      {/* Current Status */}
      {currentSession.state && (
        <div className="grid gap-4 md:grid-cols-3">
          <Card>
            <CardContent className="p-4 text-center">
              <Star className="h-8 w-8 mx-auto mb-2 text-success" />
              <p className="text-2xl font-bold text-success">{currentSession.state.matched_skills.length}</p>
              <p className="text-sm text-muted-foreground">Matched Skills</p>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="p-4 text-center">
              <AlertCircle className="h-8 w-8 mx-auto mb-2 text-warning" />
              <p className="text-2xl font-bold text-warning">{currentSession.state.missing_skills.length}</p>
              <p className="text-sm text-muted-foreground">Missing Skills</p>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="p-4 text-center">
              <TrendingUp className="h-8 w-8 mx-auto mb-2 text-primary" />
              <p className="text-2xl font-bold">{Math.round(currentSession.state.match_score * 100)}%</p>
              <p className="text-sm text-muted-foreground">Overall Match</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Analysis Section */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5" />
            Skill Gap Analysis
          </CardTitle>
        </CardHeader>
        <CardContent>
          {!skillGapData || !skillGapData.skill_resources || Object.keys(skillGapData.skill_resources).length === 0 ? (
            <div className="text-center py-8 space-y-4">
              <TrendingUp className="h-16 w-16 mx-auto text-muted-foreground" />
              <div>
                <h3 className="text-lg font-semibold mb-2">Ready to Analyze Skill Gaps</h3>
                <p className="text-muted-foreground mb-6">
                  Generate personalized learning recommendations for missing skills
                </p>
                <Button 
                  onClick={runSkillGapAnalysis} 
                  disabled={isAnalyzing}
                  size="lg"
                >
                  {isAnalyzing ? 'Analyzing...' : 'Generate Learning Recommendations'}
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Priority Skills */}
              {skillGapData.priority_skills.length > 0 && (
                <div>
                  <h3 className="font-semibold mb-3 flex items-center gap-2">
                    <Star className="h-4 w-4" />
                    Priority Skills to Develop
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {skillGapData.priority_skills.map((skill, index) => (
                      <Badge key={index} variant="default" className="bg-warning/10 text-warning border-warning/30">
                        {skill}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              {/* Learning Resources */}
              <div>
                <h3 className="font-semibold mb-4">Recommended Learning Resources</h3>
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                  {Object.entries(skillGapData.skill_resources).map(([skill, resources]) => (
                    <Card key={skill} className="hover:shadow-md transition-shadow">
                      <CardHeader className="pb-3">
                        <CardTitle className="text-base flex items-center justify-between">
                          <span>{skill}</span>
                          <Badge variant="outline" className="text-xs">
                            {Array.isArray(resources) ? resources.length : 0} resources
                          </Badge>
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-2">
                        {Array.isArray(resources) ? resources.slice(0, 3).map((resource: any, index) => {
                          const IconComponent = getResourceIcon(resource.type || 'course');
                          return (
                            <div key={index} className="flex items-start gap-2 p-2 rounded-lg hover:bg-muted/50 transition-colors">
                              <IconComponent className="h-4 w-4 mt-0.5 text-muted-foreground flex-shrink-0" />
                              <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium truncate">
                                  {resource.name || `Resource ${index + 1}`}
                                </p>
                                <p className="text-xs text-muted-foreground capitalize">
                                  {resource.type || 'course'}
                                </p>
                              </div>
                              {resource.url && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-6 w-6 p-0"
                                  onClick={() => window.open(resource.url, '_blank')}
                                >
                                  <ExternalLink className="h-3 w-3" />
                                </Button>
                              )}
                            </div>
                          );
                        }) : (
                          <p className="text-sm text-muted-foreground">No resources available</p>
                        )}
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </div>

              {/* Next Steps */}
              <div className="pt-4 border-t">
                <Button onClick={continueToAssessment} className="w-full">
                  <ClipboardList className="h-4 w-4 mr-2" />
                  Continue to Assessment Generation
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}