import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { 
  CheckCircle, 
  Award,
  MessageCircle,
  TrendingUp,
  FileText,
  Home
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useToast } from '@/hooks/use-toast';

interface InterviewResults {
  interview_score: number;
  feedback: string;
  state: {
    candidate_answers: string[];
    interview_questions: Array<{
      type: string;
      question: string;
    }>;
  };
}

export default function InterviewResults() {
  const [results, setResults] = useState<InterviewResults | null>(null);
  const navigate = useNavigate();
  const { toast } = useToast();

  useEffect(() => {
    loadResults();
  }, []);

  const loadResults = () => {
    const stored = localStorage.getItem('interview-results');
    if (stored) {
      try {
        const data = JSON.parse(stored);
        setResults(data);
      } catch (error) {
        console.error('Failed to load results:', error);
        toast({
          title: "No Results Found",
          description: "Please complete an interview first.",
          variant: "destructive",
        });
        navigate('/interviews/questions');
      }
    } else {
      toast({
        title: "No Results Found",
        description: "Please complete an interview first.",
        variant: "destructive",
      });
      navigate('/interviews/questions');
    }
  };

  const getScoreColor = (score: number) => {
    if (score >= 80) return 'text-green-600';
    if (score >= 60) return 'text-yellow-600';
    return 'text-red-600';
  };

  const getScoreLabel = (score: number) => {
    if (score >= 80) return 'Excellent';
    if (score >= 60) return 'Good';
    if (score >= 40) return 'Fair';
    return 'Needs Improvement';
  };

  if (!results) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    );
  }

  const scorePercentage = Math.round(results.interview_score * 100);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="text-center space-y-2">
        <h1 className="text-3xl font-bold text-foreground">Interview Results</h1>
        <p className="text-muted-foreground">
          Your comprehensive interview evaluation and feedback
        </p>
      </div>

      {/* Score Overview */}
      <Card className="border-primary/20">
        <CardHeader className="text-center">
          <CardTitle className="flex items-center justify-center gap-2">
            <Award className="h-6 w-6 text-primary" />
            Overall Interview Score
          </CardTitle>
        </CardHeader>
        <CardContent className="text-center space-y-4">
          <div className={`text-6xl font-bold ${getScoreColor(scorePercentage)}`}>
            {scorePercentage}%
          </div>
          <Badge 
            variant={scorePercentage >= 80 ? "default" : scorePercentage >= 60 ? "secondary" : "destructive"}
            className="text-sm"
          >
            {getScoreLabel(scorePercentage)}
          </Badge>
          <Progress value={scorePercentage} className="w-full max-w-md mx-auto" />
        </CardContent>
      </Card>

      {/* Feedback */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <MessageCircle className="h-5 w-5" />
            Detailed Feedback
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="prose prose-sm max-w-none">
            <p className="text-foreground whitespace-pre-wrap">{results.feedback}</p>
          </div>
        </CardContent>
      </Card>

      {/* Question & Answer Review */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            Interview Review
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {results.state.interview_questions.map((question, index) => (
            <div key={index} className="border rounded-lg p-4 space-y-3">
              <div className="flex items-center gap-2">
                <Badge variant="secondary">{question.type}</Badge>
                <span className="text-sm text-muted-foreground">Question {index + 1}</span>
              </div>
              
              <div>
                <h4 className="font-medium mb-2">{question.question}</h4>
                <div className="bg-muted p-3 rounded-md">
                  <div className="text-sm font-medium mb-1">Your Answer:</div>
                  <p className="text-sm text-muted-foreground">
                    {results.state.candidate_answers[index] || 'No answer provided'}
                  </p>
                </div>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Performance Insights */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5" />
            Performance Insights
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="text-center p-4 bg-primary/5 rounded-lg">
              <CheckCircle className="h-8 w-8 mx-auto mb-2 text-primary" />
              <div className="font-medium">Questions Answered</div>
              <div className="text-2xl font-bold text-primary">
                {results.state.candidate_answers.filter(a => a?.trim()).length}/{results.state.interview_questions.length}
              </div>
            </div>
            
            <div className="text-center p-4 bg-secondary/5 rounded-lg">
              <Award className="h-8 w-8 mx-auto mb-2 text-secondary-foreground" />
              <div className="font-medium">Interview Score</div>
              <div className={`text-2xl font-bold ${getScoreColor(scorePercentage)}`}>
                {scorePercentage}%
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Actions */}
      <div className="flex justify-center gap-4">
        <Button variant="outline" onClick={() => navigate('/interviews/questions')}>
          Retake Interview
        </Button>
        <Button onClick={() => navigate('/dashboard')} className="gap-2">
          <Home className="h-4 w-4" />
          Back to Dashboard
        </Button>
      </div>
    </div>
  );
}