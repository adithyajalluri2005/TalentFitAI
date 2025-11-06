import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { FileText, Home, Brain, CheckCircle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useToast } from '@/hooks/use-toast';

interface QuestionFeedback {
  question_index: number;
  review_feedback: string;
}

interface InterviewResults {
  feedback: QuestionFeedback[];
  state: {
    candidate_answers: string[];
    interview_questions: Array<{ type: string; question: string }>;
  };
}

export default function InterviewResults() {
  const [results, setResults] = useState<InterviewResults | null>(null);
  const [feedbackList, setFeedbackList] = useState<QuestionFeedback[]>([]);
  const navigate = useNavigate();
  const { toast } = useToast();

  useEffect(() => {
    const stored = localStorage.getItem('interview-results');
    if (!stored) {
      toast({
        title: 'No Results Found',
        description: 'Please complete an interview first.',
        variant: 'destructive',
      });
      navigate('/interviews/questions');
      return;
    }

    try {
      const data = JSON.parse(stored);
      setResults(data);


      const parsedFeedback =
        typeof data.feedback === 'string'
          ? JSON.parse(data.feedback)
          : data.feedback;
      if (Array.isArray(parsedFeedback)) {
        setFeedbackList(parsedFeedback);
      } else {
        setFeedbackList([]);
      }
    } catch (error) {
      console.error('Error parsing interview results:', error);
      toast({
        title: 'Error Loading Results',
        description: 'Please try retaking the interview.',
        variant: 'destructive',
      });
      navigate('/interviews/questions');
    }
  }, [navigate, toast]);

  if (!results) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="text-center space-y-2">
        <h1 className="text-3xl font-bold text-foreground">Interview Feedback</h1>
        <p className="text-muted-foreground">
          AI-generated review and insights for each question
        </p>
      </div>

      {/* Question Review */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" /> Interview Review
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {results.state.interview_questions.map((q, i) => {
            const feedback =
              feedbackList.find((f) => f.question_index === i + 1)?.review_feedback ||
              'No specific AI feedback generated for this question.';

            return (
              <div key={i} className="border rounded-lg p-4 space-y-3">
                {/* Question Header */}
                <div className="flex items-center gap-2">
                  <Badge variant="secondary">{q.type}</Badge>
                  <span className="text-sm text-muted-foreground">
                    Question {i + 1}
                  </span>
                </div>

                {/* Question */}
                <h4 className="font-medium mb-2">{q.question}</h4>

                {/* User Answer */}
                <div className="bg-muted p-3 rounded-md">
                  <div className="text-sm font-medium mb-1">Your Answer:</div>
                  {results.state.candidate_answers[i]?.trim() ? (
                    <p className="text-sm text-foreground whitespace-pre-wrap">
                      {results.state.candidate_answers[i]}
                    </p>
                  ) : (
                    <p className="text-sm text-muted-foreground italic">
                      No answer provided
                    </p>
                  )}
                </div>

                {/* AI Feedback */}
                <div className="bg-blue-50 p-3 rounded-md border border-blue-200">
                  <div className="flex items-center gap-2 text-blue-700 mb-1">
                    <Brain className="h-4 w-4" />
                    <span className="font-medium text-sm">AI Feedback:</span>
                  </div>
                  <p className="text-sm text-blue-800 whitespace-pre-wrap">
                    {feedback}
                  </p>
                </div>
              </div>
            );
          })}
        </CardContent>
      </Card>

      {/* Summary */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CheckCircle className="h-5 w-5" /> Summary
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center p-4 bg-primary/5 rounded-lg">
            <div className="font-medium">Questions Answered</div>
            <div className="text-2xl font-bold text-primary">
              {results.state.candidate_answers.filter((a) => a?.trim()).length}/
              {results.state.interview_questions.length}
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
          <Home className="h-4 w-4" /> Back to Dashboard
        </Button>
      </div>
    </div>
  );
}
