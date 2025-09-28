import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Label } from '@/components/ui/label';
import { 
  ClipboardList, 
  CheckCircle,
  X,
  Brain,
  MessageCircle,
  Download
} from 'lucide-react';
import { apiService, CandidateState, MCQQuestion } from '@/services/api';
import { useToast } from '@/hooks/use-toast';
import { useNavigate } from 'react-router-dom';

export default function CreateAssessment() {
  const [currentSession, setCurrentSession] = useState<{
    threadId?: string;
    state?: CandidateState;
  }>({});
  const [isGenerating, setIsGenerating] = useState(false);
  const [assessmentData, setAssessmentData] = useState<CandidateState | null>(null);
  const [selectedAnswers, setSelectedAnswers] = useState<Record<number, string>>({});
  const [showResults, setShowResults] = useState(false);
  
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

        // If we already have assessment data, show it
        if (session.state?.mcqs && session.state.mcqs.length > 0) {
          setAssessmentData(session.state);
        }
      } catch (error) {
        console.error('Failed to load session:', error);
      }
    }
  };

  const generateAssessment = async () => {
    if (!currentSession.threadId || !currentSession.state) {
      toast({
        title: "Missing Information",
        description: "Please complete the previous steps first",
        variant: "destructive",
      });
      return;
    }
    
    setIsGenerating(true);
    
    try {
      const response = await apiService.generateAssessment({
        state: currentSession.state,
        thread_id: currentSession.threadId
      });
      
      setAssessmentData(response.state);
      
      // Update session in localStorage
      const updatedSession = {
        threadId: response.thread_id,
        state: response.state,
        progress: 85
      };
      localStorage.setItem('talentai-session', JSON.stringify(updatedSession));
      setCurrentSession(updatedSession);
      
      toast({
        title: "Assessment Generated",
        description: `Created ${response.mcqs.length} questions based on required skills`,
      });
      
    } catch (error) {
      toast({
        title: "Generation Failed",
        description: "Failed to generate assessment. Please try again.",
        variant: "destructive",
      });
    } finally {
      setIsGenerating(false);
    }
  };

  const calculateScore = () => {
    if (!assessmentData?.mcqs) return 0;
    
    let correct = 0;
    assessmentData.mcqs.forEach((question, index) => {
      if (selectedAnswers[index] === question.answer) {
        correct++;
      }
    });
    
    return Math.round((correct / assessmentData.mcqs.length) * 100);
  };

  const submitAssessment = () => {
    const score = calculateScore();
    setShowResults(true);
    
    toast({
      title: "Assessment Completed",
      description: `Score: ${score}%`,
    });
  };

  const continueToInterview = () => {
    navigate('/interviews/questions');
  };

  const exportAssessment = () => {
    if (!assessmentData?.mcqs) return;
    
    const assessmentText = assessmentData.mcqs.map((q, index) => {
      return `Question ${index + 1}: ${q.question}\n${q.options.map((opt, i) => `${String.fromCharCode(65 + i)}) ${opt}`).join('\n')}\nCorrect Answer: ${q.answer}\nExplanation: ${q.explanation}\n\n`;
    }).join('');
    
    const blob = new Blob([assessmentText], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'candidate-assessment.txt';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Assessment Generation</h1>
        <p className="text-muted-foreground">
          Generate and preview AI-powered multiple choice questions based on job requirements
        </p>
      </div>

      {/* Assessment Status */}
      {currentSession.state && (
        <Card className="border-primary/20 bg-primary/5">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">Based on Skills</p>
                <div className="flex flex-wrap gap-1 mt-2">
                  {(currentSession.state.based_on_skills.length > 0 ? 
                    currentSession.state.based_on_skills : 
                    currentSession.state.missing_skills.slice(0, 5)
                  ).map((skill, index) => (
                    <Badge key={index} variant="secondary" className="text-xs">
                      {skill}
                    </Badge>
                  ))}
                </div>
              </div>
              <div className="text-right">
                <p className="text-sm text-muted-foreground">Match Score</p>
                <p className="text-lg font-semibold">{Math.round(currentSession.state.match_score * 100)}%</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Assessment Generation/Display */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ClipboardList className="h-5 w-5" />
            MCQ Assessment
          </CardTitle>
        </CardHeader>
        <CardContent>
          {!assessmentData || !assessmentData.mcqs || assessmentData.mcqs.length === 0 ? (
            <div className="text-center py-8 space-y-4">
              <Brain className="h-16 w-16 mx-auto text-muted-foreground" />
              <div>
                <h3 className="text-lg font-semibold mb-2">Ready to Generate Assessment</h3>
                <p className="text-muted-foreground mb-6">
                  Create multiple choice questions to test candidate knowledge on required skills
                </p>
                <Button 
                  onClick={generateAssessment} 
                  disabled={isGenerating}
                  size="lg"
                >
                  {isGenerating ? 'Generating Questions...' : 'Generate Assessment'}
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Assessment Header */}
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-semibold">Generated Assessment</h3>
                  <p className="text-sm text-muted-foreground">
                    {assessmentData.mcqs.length} questions • Multiple choice
                  </p>
                </div>
                <Button variant="outline" size="sm" onClick={exportAssessment}>
                  <Download className="h-4 w-4 mr-2" />
                  Export
                </Button>
              </div>

              {/* Questions */}
              <div className="space-y-6">
                {assessmentData.mcqs.map((question, questionIndex) => (
                  <Card key={questionIndex} className="border-l-4 border-l-primary">
                    <CardContent className="p-4">
                      <div className="space-y-4">
                        <div>
                          <h4 className="font-medium mb-2">
                            Question {questionIndex + 1}
                          </h4>
                          <p className="text-sm">{question.question}</p>
                        </div>
                        
                        <RadioGroup
                          value={selectedAnswers[questionIndex] || ''}
                          onValueChange={(value) => 
                            setSelectedAnswers(prev => ({ ...prev, [questionIndex]: value }))
                          }
                          disabled={showResults}
                        >
                          <div className="grid gap-2">
                            {question.options.map((option, optionIndex) => {
                              const isCorrect = option === question.answer;
                              const isSelected = selectedAnswers[questionIndex] === option;
                              
                              return (
                                <div 
                                  key={optionIndex} 
                                  className={`flex items-center space-x-2 p-2 rounded-lg border ${
                                    showResults 
                                      ? isCorrect 
                                        ? 'border-success bg-success/5' 
                                        : isSelected 
                                        ? 'border-destructive bg-destructive/5' 
                                        : 'border-border'
                                      : 'border-border hover:border-primary/50'
                                  }`}
                                >
                                  <RadioGroupItem value={option} id={`q${questionIndex}-${optionIndex}`} />
                                  <Label 
                                    htmlFor={`q${questionIndex}-${optionIndex}`}
                                    className="flex-1 cursor-pointer"
                                  >
                                    {option}
                                  </Label>
                                  {showResults && isCorrect && (
                                    <CheckCircle className="h-4 w-4 text-success" />
                                  )}
                                  {showResults && isSelected && !isCorrect && (
                                    <X className="h-4 w-4 text-destructive" />
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </RadioGroup>
                        
                        {showResults && (
                          <div className="mt-4 p-3 bg-muted/50 rounded-lg">
                            <p className="text-sm">
                              <span className="font-medium">Explanation:</span> {question.explanation}
                            </p>
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>

              {/* Assessment Actions */}
              <div className="flex gap-4 pt-4 border-t">
                {!showResults ? (
                  <Button 
                    onClick={submitAssessment}
                    disabled={Object.keys(selectedAnswers).length < assessmentData.mcqs.length}
                  >
                    Submit Assessment
                  </Button>
                ) : (
                  <div className="flex items-center justify-between w-full">
                    <div className="flex items-center gap-4">
                      <div className="text-center">
                        <p className="text-2xl font-bold">{calculateScore()}%</p>
                        <p className="text-sm text-muted-foreground">Score</p>
                      </div>
                      <div className="text-center">
                        <p className="text-lg font-semibold">
                          {Object.values(selectedAnswers).filter((answer, index) => 
                            answer === assessmentData.mcqs[index].answer
                          ).length} / {assessmentData.mcqs.length}
                        </p>
                        <p className="text-sm text-muted-foreground">Correct</p>
                      </div>
                    </div>
                    <Button onClick={continueToInterview}>
                      <MessageCircle className="h-4 w-4 mr-2" />
                      Continue to Interview
                    </Button>
                  </div>
                )}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}