import { useState, useEffect, useRef, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { Progress } from '@/components/ui/progress';
import { 
  MessageCircle, 
  Send,
  Brain,
  CheckCircle,
  Mic,
  MicOff,
  Video,
  VideoOff,
  Play,
  Square
} from 'lucide-react';
import { apiService, CandidateState, InterviewQuestion } from '@/services/api';
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
  const [transcript, setTranscript] = useState('');
  
  // Refs for media
  const videoRef = useRef<HTMLVideoElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recognitionRef = useRef<any>(null);
  const streamRef = useRef<MediaStream | null>(null);
  
  const { toast } = useToast();
  const navigate = useNavigate();

  useEffect(() => {
    loadSessionFromStorage();
    setupSpeechRecognition();
    
    // Cleanup on unmount
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
      }
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
    };
  }, []);

  const loadSessionFromStorage = () => {
    const stored = localStorage.getItem('talentai-session');
    if (stored) {
      try {
        const session = JSON.parse(stored);
        setCurrentSession(session);

        // If we already have interview data, show it
        if (session.state?.interview_questions && session.state.interview_questions.length > 0) {
          setInterviewData(session.state);
          // Initialize answers array
          setAnswers(new Array(session.state.interview_questions.length).fill(''));
        }
      } catch (error) {
        console.error('Failed to load session:', error);
      }
    }
  };

  const generateInterview = async () => {
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
      const response = await apiService.generateInterview({
        state: currentSession.state,
        thread_id: currentSession.threadId
      });
      
      setInterviewData(response.state);
      setAnswers(new Array(response.interview_questions.length).fill(''));
      
      // Update session in localStorage
      const updatedSession = {
        threadId: response.thread_id,
        state: response.state,
        progress: 100
      };
      localStorage.setItem('talentai-session', JSON.stringify(updatedSession));
      setCurrentSession(updatedSession);
      
      toast({
        title: "Interview Generated",
        description: `Created ${response.interview_questions.length} interview questions`,
      });
      
    } catch (error) {
      toast({
        title: "Generation Failed",
        description: "Failed to generate interview questions. Please try again.",
        variant: "destructive",
      });
    } finally {
      setIsGenerating(false);
    }
  };

  const saveAnswer = () => {
    const newAnswers = [...answers];
    newAnswers[currentQuestionIndex] = currentAnswer;
    setAnswers(newAnswers);
    setCurrentAnswer('');
    
    toast({
      title: "Answer Saved",
      description: `Answer for question ${currentQuestionIndex + 1} saved`,
    });
  };

  const nextQuestion = () => {
    if (currentQuestionIndex < (interviewData?.interview_questions.length || 0) - 1) {
      setCurrentQuestionIndex(prev => prev + 1);
      setCurrentAnswer(answers[currentQuestionIndex + 1] || '');
    }
  };

  const prevQuestion = () => {
    if (currentQuestionIndex > 0) {
      setCurrentQuestionIndex(prev => prev - 1);
      setCurrentAnswer(answers[currentQuestionIndex - 1] || '');
    }
  };

  const setupSpeechRecognition = () => {
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
      const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      recognitionRef.current = new SpeechRecognition();
      recognitionRef.current.continuous = true;
      recognitionRef.current.interimResults = true;
      recognitionRef.current.lang = 'en-US';
      
      recognitionRef.current.onresult = (event) => {
        let finalTranscript = '';
        let interimTranscript = '';
        
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const transcript = event.results[i][0].transcript;
          if (event.results[i].isFinal) {
            finalTranscript += transcript;
          } else {
            interimTranscript += transcript;
          }
        }
        
        const fullTranscript = finalTranscript + interimTranscript;
        setTranscript(fullTranscript);
        setCurrentAnswer(fullTranscript);
      };
      
      recognitionRef.current.onerror = (event) => {
        console.error('Speech recognition error:', event.error);
        toast({
          title: "Speech Recognition Error",
          description: "There was an issue with speech recognition. Please try again.",
          variant: "destructive",
        });
      };
    }
  };

  const startVideo = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ 
        video: true, 
        audio: true 
      });
      streamRef.current = stream;
      
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
      
      setIsVideoEnabled(true);
    } catch (error) {
      toast({
        title: "Camera Access Denied",
        description: "Please allow camera access to record video responses.",
        variant: "destructive",
      });
    }
  };

  // Auto-start camera when interview data is available
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
      toast({
        title: "No Camera/Microphone",
        description: "Please enable camera first to start recording.",
        variant: "destructive",
      });
      return;
    }

    setIsRecording(true);
    setTranscript('');
    setCurrentAnswer('');
    
    // Start speech recognition
    if (recognitionRef.current) {
      recognitionRef.current.start();
    }

    // Start media recording
    mediaRecorderRef.current = new MediaRecorder(streamRef.current);
    const recordedChunks: Blob[] = [];
    
    mediaRecorderRef.current.ondataavailable = (event) => {
      if (event.data.size > 0) {
        recordedChunks.push(event.data);
      }
    };
    
    mediaRecorderRef.current.onstop = () => {
      const blob = new Blob(recordedChunks, { type: 'video/webm' });
      console.log('Recording stopped, blob size:', blob.size);
    };
    
    mediaRecorderRef.current.start();
  };

  const stopRecording = () => {
    setIsRecording(false);
    
    // Stop speech recognition
    if (recognitionRef.current) {
      recognitionRef.current.stop();
    }
    
    // Stop media recording
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
    
    // Finalize the transcribed answer
    if (transcript) {
      setCurrentAnswer(transcript);
    }
    setTranscript('');
  };

  const submitInterview = async () => {
    if (!currentSession.threadId || !currentSession.state) return;
    
    try {
      // Filter out empty answers
      const validAnswers = answers.filter(answer => answer.trim().length > 0);
      
      const response = await apiService.evaluateInterview({
        state: { ...currentSession.state, candidate_answers: validAnswers },
        thread_id: currentSession.threadId
      });
      
      // Store results in localStorage for the results page
      const results = {
        interview_score: response.interview_score,
        feedback: response.feedback,
        state: {
          candidate_answers: validAnswers,
          interview_questions: interviewData?.interview_questions || []
        }
      };
      localStorage.setItem('interview-results', JSON.stringify(results));
      
      toast({
        title: "Interview Submitted",
        description: `Interview evaluated with score: ${Math.round((response.interview_score || 0) * 100)}%`,
      });
      
      // Navigate to results page
      navigate('/interviews/results');
      
    } catch (error) {
      toast({
        title: "Submission Failed",
        description: "Failed to submit interview answers.",
        variant: "destructive",
      });
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Interview Questions</h1>
        <p className="text-muted-foreground">
          Generate interview questions and provide recorded answers for candidate evaluation
        </p>
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
                    <CardContent className="space-y-4">
                      <div className="text-center">
                        <Button
                          variant={isRecording ? "destructive" : "default"}
                          onClick={isRecording ? stopRecording : startRecording}
                          disabled={!isVideoEnabled}
                          className="gap-2"
                          size="lg"
                        >
                          {isRecording ? <Square className="h-5 w-5" /> : <Mic className="h-5 w-5" />}
                          {isRecording ? 'Stop Recording' : 'Record Answer'}
                        </Button>
                        <p className="text-sm text-muted-foreground mt-2">
                          {isRecording ? 'Recording your response...' : 'Click to record your answer'}
                        </p>
                      </div>
                      
                      {transcript && (
                        <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                          <div className="text-sm font-medium text-blue-800 mb-1">Live Transcript:</div>
                          <div className="text-sm text-blue-700">{transcript}</div>
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

                  {/* Answer Input */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">Your Answer</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div>
                        <label className="text-sm font-medium mb-2 block">
                          Transcribed answer (you can edit if needed)
                        </label>
                        <Textarea
                          value={currentAnswer}
                          onChange={(e) => setCurrentAnswer(e.target.value)}
                          placeholder="Your recorded answer will appear here..."
                          className="min-h-[200px] resize-none"
                        />
                      </div>

                      <Button 
                        onClick={saveAnswer}
                        disabled={!currentAnswer.trim()}
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
                      disabled={currentQuestionIndex === 0}
                      variant="outline"
                    >
                      Previous Question
                    </Button>
                    
                    {currentQuestionIndex < interviewData.interview_questions.length - 1 ? (
                      <Button onClick={nextQuestion}>
                        Next Question
                      </Button>
                    ) : (
                      <Button 
                        onClick={submitInterview}
                        disabled={answers.filter(a => a.trim()).length === 0}
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