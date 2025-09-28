import { useState } from 'react';
import { useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { 
  Upload, 
  FileText, 
  CheckCircle, 
  X,
  User,
  Briefcase,
  GraduationCap,
  Star
} from 'lucide-react';
import { apiService, CandidateState } from '@/services/api';
import { useToast } from '@/hooks/use-toast';
import { useNavigate } from 'react-router-dom';

export default function UploadResume() {
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [candidateData, setCandidateData] = useState<CandidateState | null>(null);
  const [threadId, setThreadId] = useState<string>('');
  
  const { toast } = useToast();
  const navigate = useNavigate();

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const file = acceptedFiles[0];
    if (file) {
      setUploadedFile(file);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'application/msword': ['.doc']
    },
    maxFiles: 1,
    maxSize: 10 * 1024 * 1024, // 10MB
  });

  const processResume = async () => {
    if (!uploadedFile) return;
    
    setIsProcessing(true);
    setProgress(10);
    
    try {
      const response = await apiService.uploadResume(uploadedFile);
      setProgress(100);
      
      setCandidateData(response.state);
      setThreadId(response.thread_id);
      
      // Save session to localStorage
      localStorage.setItem('talentai-session', JSON.stringify({
        threadId: response.thread_id,
        state: response.state,
        progress: 20
      }));
      
      toast({
        title: "Resume Processed Successfully",
        description: `Identified ${response.resume_skills.length} skills from the resume`,
      });
      
    } catch (error) {
      toast({
        title: "Processing Failed",
        description: "Failed to process the resume. Please try again.",
        variant: "destructive",
      });
    } finally {
      setIsProcessing(false);
    }
  };

  const removeFile = () => {
    setUploadedFile(null);
    setCandidateData(null);
    setProgress(0);
  };

  const continueToJD = () => {
    navigate('/jobs/upload-jd');
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Upload Resume</h1>
        <p className="text-muted-foreground">
          Upload a candidate's resume to extract skills and experience using AI analysis
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Upload Section */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Upload className="h-5 w-5" />
              Resume Upload
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {!uploadedFile ? (
              <div
                {...getRootProps()}
                className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
                  isDragActive
                    ? 'border-primary bg-primary/5'
                    : 'border-muted-foreground/25 hover:border-primary/50'
                }`}
              >
                <input {...getInputProps()} />
                <FileText className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
                <h3 className="text-lg font-semibold mb-2">
                  {isDragActive ? 'Drop the file here' : 'Drag & drop resume here'}
                </h3>
                <p className="text-muted-foreground mb-4">
                  or click to select a file
                </p>
                <p className="text-sm text-muted-foreground">
                  Supports PDF, DOC, DOCX (max 10MB)
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex items-center justify-between p-4 bg-muted/50 rounded-lg">
                  <div className="flex items-center gap-3">
                    <FileText className="h-8 w-8 text-primary" />
                    <div>
                      <p className="font-medium">{uploadedFile.name}</p>
                      <p className="text-sm text-muted-foreground">
                        {(uploadedFile.size / 1024 / 1024).toFixed(2)} MB
                      </p>
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={removeFile}
                    disabled={isProcessing}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>

                {isProcessing && (
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span>Processing resume...</span>
                      <span>{progress}%</span>
                    </div>
                    <Progress value={progress} />
                  </div>
                )}

                {!candidateData && (
                  <Button 
                    onClick={processResume} 
                    disabled={isProcessing}
                    className="w-full"
                  >
                    {isProcessing ? 'Processing...' : 'Process Resume'}
                  </Button>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Results Section */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <User className="h-5 w-5" />
              Extracted Information
            </CardTitle>
          </CardHeader>
          <CardContent>
            {!candidateData ? (
              <div className="text-center py-8">
                <User className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
                <p className="text-muted-foreground">
                  Upload and process a resume to see extracted information
                </p>
              </div>
            ) : (
              <div className="space-y-6">
                {/* Skills */}
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <Star className="h-4 w-4" />
                    <h3 className="font-semibold">Skills Identified</h3>
                    <Badge variant="secondary">{candidateData.candidate_skills.length}</Badge>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {candidateData.candidate_skills.slice(0, 15).map((skill, index) => (
                      <Badge key={index} variant="outline">
                        {skill}
                      </Badge>
                    ))}
                    {candidateData.candidate_skills.length > 15 && (
                      <Badge variant="secondary">
                        +{candidateData.candidate_skills.length - 15} more
                      </Badge>
                    )}
                  </div>
                </div>

                {/* Education */}
                {candidateData.education.length > 0 && (
                  <div>
                    <div className="flex items-center gap-2 mb-3">
                      <GraduationCap className="h-4 w-4" />
                      <h3 className="font-semibold">Education</h3>
                    </div>
                    <div className="space-y-2">
                      {candidateData.education.map((edu, index) => (
                        <p key={index} className="text-sm text-muted-foreground">
                          {edu}
                        </p>
                      ))}
                    </div>
                  </div>
                )}

                {/* Experience */}
                {candidateData.candidate_experience && (
                  <div>
                    <div className="flex items-center gap-2 mb-3">
                      <Briefcase className="h-4 w-4" />
                      <h3 className="font-semibold">Experience Level</h3>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      {candidateData.candidate_experience}
                    </p>
                  </div>
                )}

                {/* Next Steps */}
                <div className="pt-4 border-t">
                  <div className="flex items-center gap-2 mb-3">
                    <CheckCircle className="h-4 w-4 text-success" />
                    <span className="text-sm font-medium">Resume processed successfully</span>
                  </div>
                  <Button onClick={continueToJD} className="w-full">
                    Continue to Job Description Upload
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