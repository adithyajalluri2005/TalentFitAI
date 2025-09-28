import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import UploadResume from "./pages/candidates/UploadResume";
import UploadJD from "./pages/jobs/UploadJD";
import Matching from "./pages/Matching";
import SkillGap from "./pages/SkillGap";
import CreateAssessment from "./pages/assessments/CreateAssessment";
import InterviewQuestions from "./pages/interviews/InterviewQuestions";
import InterviewResults from "./pages/interviews/InterviewResults";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <Layout>
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/candidates/upload-resume" element={<UploadResume />} />
            <Route path="/jobs/upload-jd" element={<UploadJD />} />
            <Route path="/matching" element={<Matching />} />
            <Route path="/skill-gap" element={<SkillGap />} />
            <Route path="/assessments/create" element={<CreateAssessment />} />
            <Route path="/interviews/questions" element={<InterviewQuestions />} />
            <Route path="/interviews/results" element={<InterviewResults />} />
            {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Layout>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;