import { useState, useEffect, useRef, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { 
  MessageCircle, 
  Send,
  Brain,
  CheckCircle,
  Mic,
  Video,
  Square,
  Loader2 
} from 'lucide-react';
import { apiService, CandidateState } from '@/services/api';
import { useToast } from '@/hooks/use-toast';
import { useNavigate } from 'react-router-dom';

export default function InterviewQuestions() {
  const [currentSession, setCurrentSession] = useState<{
    threadId?: string;
    state?: CandidateState;
  }>({});
  const [isGenerating, setIsGenerating] = useState(false);
  const [interviewData, setInterviewData] = useState<CandidateState | null>(null);
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
  const [answers, setAnswers] = useState<string[]>([]);
  const [currentAnswer, setCurrentAnswer] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [isVideoEnabled, setIsVideoEnabled] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [recordedBlob, setRecordedBlob] = useState<Blob | null>(null);

  // ⏱ Timer states
  const [timeLeft, setTimeLeft] = useState(15 * 60); // 15 minutes in seconds
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  const videoRef = useRef<HTMLVideoElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const { toast } = useToast();
  const navigate = useNavigate();

  useEffect(() => {
    loadSessionFromStorage();
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
      }
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  const loadSessionFromStorage = () => {
    const stored = localStorage.getItem('talentai-session');
    if (stored) {
      try {
        const session = JSON.parse(stored);
        setCurrentSession(session);
        if (session.state?.interview_questions && session.state.interview_questions.length > 0) {
          setInterviewData(session.state);
          setAnswers(new Array(session.state.interview_questions.length).fill(''));
        }
      } catch (error) {
        console.error('Failed to load session:', error);
      }
    }
  };

  const generateInterview = async () => {
    if (!currentSession.threadId || !currentSession.state) {
      toast({ title: "Missing Information", description: "Please complete the previous steps first", variant: "destructive" });
      return;
    }

    setIsGenerating(true);
    try {
      const response = await apiService.generateInterview({
        state: currentSession.state,
        thread_id: currentSession.threadId
      });

      setInterviewData(response.state);
      setAnswers(new Array(response.interview_questions.length).fill(''));

      const updatedSession = {
        threadId: response.thread_id,
        state: response.state,
        progress: 100
      };
      localStorage.setItem('talentai-session', JSON.stringify(updatedSession));
      setCurrentSession(updatedSession);

      toast({ title: "Interview Generated", description: `Created ${response.interview_questions.length} interview questions` });

      // Start the timer when interview is generated
      startTimer();

    } catch (error) {
      toast({ title: "Generation Failed", description: "Failed to generate interview questions. Please try again.", variant: "destructive" });
    } finally {
      setIsGenerating(false);
    }
  };

  // ⏱ Timer function
  const startTimer = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    setTimeLeft(15 * 60);
    timerRef.current = setInterval(() => {
      setTimeLeft(prev => {
        if (prev <= 1) {
          clearInterval(timerRef.current!);
          toast({ title: "Time's Up!", description: "Interview auto-submitted after 15 minutes." });
          submitInterview();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  }, []);

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const saveAnswer = () => {
    const newAnswers = [...answers];
    newAnswers[currentQuestionIndex] = currentAnswer;
    setAnswers(newAnswers);
    setCurrentAnswer('');
    setRecordedBlob(null);
    toast({ title: "Answer Saved", description: `Answer for question ${currentQuestionIndex + 1} saved` });
  };

  const nextQuestion = () => {
    saveAnswer();
    if (currentQuestionIndex < (interviewData?.interview_questions.length || 0) - 1) {
      setCurrentQuestionIndex(prev => prev + 1);
      setCurrentAnswer(answers[currentQuestionIndex + 1] || '');
      setRecordedBlob(null);
      setIsTranscribing(false);
    }
  };

  const prevQuestion = () => {
    saveAnswer();
    if (currentQuestionIndex > 0) {
      setCurrentQuestionIndex(prev => prev - 1);
      setCurrentAnswer(answers[currentQuestionIndex - 1] || '');
      setRecordedBlob(null);
      setIsTranscribing(false);
    }
  };

  const startVideo = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
      setIsVideoEnabled(true);
    } catch (error) {
      toast({ title: "Camera/Mic Access Denied", description: "Please allow camera and microphone access to record responses.", variant: "destructive" });
    }
  };

  useEffect(() => {
    if (interviewData && !isVideoEnabled) {
      startVideo();
    }
  }, [interviewData, isVideoEnabled]);

  const stopVideo = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
    setIsVideoEnabled(false);
    setIsRecording(false);
  };

  const startRecording = () => {
    if (!streamRef.current) {
      toast({ title: "No Camera/Microphone", description: "Please enable camera and microphone first to start recording.", variant: "destructive" });
      return;
    }

    setIsRecording(true);
    setCurrentAnswer('');
    setRecordedBlob(null);
    setIsTranscribing(false);

    mediaRecorderRef.current = new MediaRecorder(streamRef.current, { mimeType: 'video/webm' });
    const recordedChunks: Blob[] = [];

    mediaRecorderRef.current.ondataavailable = (event) => {
      if (event.data.size > 0) recordedChunks.push(event.data);
    };

    mediaRecorderRef.current.onstop = async () => {
      const blob = new Blob(recordedChunks, { type: 'video/webm' });

      setIsTranscribing(true);
      if (!currentSession.threadId) {
        toast({ title: "Error", description: "Session ID is missing for transcription.", variant: "destructive" });
        setIsTranscribing(false);
        return;
      }

      try {
        const response = await apiService.transcribeGroq(
          currentSession.threadId,
          currentQuestionIndex,
          blob
        );
        setCurrentAnswer(response.text);
        setRecordedBlob(blob);
        toast({ title: "Transcription Complete", description: "Answer successfully transcribed" });
      } catch (e) {
        const errorMessage = e instanceof Error ? e.message : "An unknown error occurred.";
        setCurrentAnswer(`[Transcription Failed: ${errorMessage}]`);
        toast({ title: "Transcription Failed", description: errorMessage, variant: "destructive" });
      } finally {
        setIsTranscribing(false);
      }
    };

    mediaRecorderRef.current.start();
  };

  const stopRecording = () => {
    setIsRecording(false);
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
  };

  const submitInterview = async () => {
    if (!currentSession.threadId || !currentSession.state) return;

    saveAnswer();
    try {
      const answersToSend = answers;
      const response = await apiService.evaluateInterview({
        state: { 
          ...currentSession.state, 
          candidate_answers: answersToSend,
          interview_questions: interviewData?.interview_questions || []
        },
        thread_id: currentSession.threadId
      });

      const results = {
        interview_score: response.interview_score,
        feedback: response.feedback,
        state: {
          candidate_answers: answersToSend, 
          interview_questions: interviewData?.interview_questions || []
        }
      };
      localStorage.setItem('interview-results', JSON.stringify(results));
      toast({ title: "Interview Submitted", description: `Interview evaluated with score: ${Math.round((response.interview_score || 0) * 100)}%` });
      navigate('/interviews/results');
    } catch (error) {
      toast({ title: "Submission Failed", description: "Failed to submit interview answers.", variant: "destructive" });
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Interview Questions</h1>
          <p className="text-muted-foreground">
            Generate interview questions and provide recorded answers for candidate evaluation
          </p>
        </div>

        {/* Timer Display */}
        {interviewData && interviewData.interview_questions?.length > 0 && (
          <div className="bg-blue-50 text-blue-800 px-4 py-2 rounded-md font-semibold">
            ⏱ Time Left: {formatTime(timeLeft)}
          </div>
        )}
      </div>

      {/* Interview Generation/Display */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <MessageCircle className="h-5 w-5" />
            AI Interview Assistant
          </CardTitle>
        </CardHeader>
        <CardContent>
          {!interviewData || !interviewData.interview_questions || interviewData.interview_questions.length === 0 ? (
            <div className="text-center py-8 space-y-4">
              <Brain className="h-16 w-16 mx-auto text-muted-foreground" />
              <div>
                <h3 className="text-lg font-semibold mb-2">Ready to Generate Interview</h3>
                <p className="text-muted-foreground mb-6">
                  Create personalized interview questions based on the job requirements and candidate profile
                </p>
                <Button 
                  onClick={generateInterview} 
                  disabled={isGenerating}
                  size="lg"
                >
                  {isGenerating ? 'Generating Questions...' : 'Generate Interview Questions'}
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Progress */}
              <div>
                <div className="flex justify-between text-sm mb-2">
                  <span>Interview Progress</span>
                  <span>{currentQuestionIndex + 1} of {interviewData.interview_questions.length}</span>
                </div>
                <Progress value={((currentQuestionIndex + 1) / interviewData.interview_questions.length) * 100} />
              </div>

              {/* Main Interview Layout - Camera Left, Questions Right */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Left Side - Video Feed */}
                <div className="space-y-4">
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">Live Video Feed</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="relative">
                        <video
                          ref={videoRef}
                          autoPlay
                          muted
                          className="w-full h-80 bg-black rounded-lg object-cover"
                          style={{ display: isVideoEnabled ? 'block' : 'none' }}
                        />
                        {!isVideoEnabled && (
                          <div className="w-full h-80 bg-muted rounded-lg flex items-center justify-center">
                            <div className="text-center">
                              <Video className="h-12 w-12 mx-auto mb-2 text-muted-foreground" />
                              <p className="text-muted-foreground">Starting camera...</p>
                            </div>
                          </div>
                        )}
                        {isRecording && (
                          <div className="absolute top-4 right-4 flex items-center gap-2 bg-red-500 text-white px-3 py-1 rounded-full">
                            <div className="w-2 h-2 bg-white rounded-full animate-pulse" />
                            <span className="text-sm">Recording</span>
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>

                  {/* Recording Controls */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">Record Your Answer</CardTitle>
                    </CardHeader>
                    <CardContent className="text-center space-y-4">
                      <Button
                        variant={isRecording ? "destructive" : "default"}
                        onClick={isRecording ? stopRecording : startRecording}
                        disabled={!isVideoEnabled || isTranscribing}
                        className="gap-2"
                        size="lg"
                      >
                        {isRecording ? <Square className="h-5 w-5" /> : <Mic className="h-5 w-5" />}
                        {isRecording ? 'Stop Recording' : 'Record Answer'}
                      </Button>
                      <p className="text-sm text-muted-foreground mt-2">
                        {isRecording ? 'Recording your response...' : (isTranscribing ? 'Awaiting Transcription...' : 'Click to record your answer')}
                      </p>
                      
                      {isTranscribing && (
                        <div className="flex items-center justify-center p-3 bg-blue-50 border border-blue-200 rounded-lg">
                          <Loader2 className="h-4 w-4 animate-spin mr-2 text-blue-700" />
                          <span className="text-sm font-medium text-blue-800">Transcribing...</span>
                        </div>
                      )}
                      
                    </CardContent>
                  </Card>
                </div>

                {/* Right Side - Questions and Answers */}
                <div className="space-y-4">
                  {/* Current Question */}
                  <Card className="border-l-4 border-l-primary">
                    <CardContent className="p-6">
                      <div className="space-y-4">
                        <div className="flex items-center gap-2">
                          <Badge variant="secondary">
                            {interviewData.interview_questions[currentQuestionIndex].type}
                          </Badge>
                          <span className="text-sm text-muted-foreground">
                            Question {currentQuestionIndex + 1}
                          </span>
                        </div>
                        
                        <h3 className="text-lg font-medium">
                          {interviewData.interview_questions[currentQuestionIndex].question}
                        </h3>
                      </div>
                    </CardContent>
                  </Card>

                  {/* Answer Display and Save Button - TEXTAREA REMOVED */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">Transcribed Answer</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="p-4 bg-muted border rounded-lg min-h-[150px]">
                        <p className="text-sm text-foreground whitespace-pre-wrap">
                          {currentAnswer || (isTranscribing ? "Transcription in progress..." : "No recorded answer for this question.")}
                        </p>
                      </div>

                      <Button 
                        onClick={saveAnswer}
                        disabled={!currentAnswer.trim() || isTranscribing}
                        className="gap-2"
                      >
                        <CheckCircle className="h-4 w-4" />
                        Save Answer
                      </Button>
                    </CardContent>
                  </Card>

                  {/* Navigation */}
                  <div className="flex justify-between">
                    <Button
                      onClick={prevQuestion}
                      disabled={currentQuestionIndex === 0 || isTranscribing}
                      variant="outline"
                    >
                      Previous Question
                    </Button>
                    
                    {currentQuestionIndex < interviewData.interview_questions.length - 1 ? (
                      <Button onClick={nextQuestion} disabled={isTranscribing}>
                        Next Question
                      </Button>
                    ) : (
                      <Button 
                        onClick={submitInterview}
                        disabled={answers.filter(a => a.trim()).length === 0 || isTranscribing}
                        className="gap-2"
                      >
                        <Send className="h-4 w-4" />
                        Submit Interview
                      </Button>
                    )}
                  </div>
                </div>
              </div>

              {/* Answer Summary */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Answer Summary</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid gap-2">
                    {interviewData.interview_questions.map((_, index) => (
                      <div key={index} className="flex items-center gap-2">
                        <span className="text-sm w-16">Q{index + 1}:</span>
                        <div className="flex items-center gap-2">
                           {answers[index]?.trim() ? (
                            <CheckCircle className="h-4 w-4 text-green-500" />
                          ) : (
                            <div className="h-4 w-4 rounded-full border-2 border-muted-foreground" />
                          )}
                          <span className="text-sm text-muted-foreground">
                            {answers[index]?.trim() ? 'Answered' : 'Not answered'}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}