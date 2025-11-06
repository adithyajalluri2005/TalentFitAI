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

// NEW IMPORTS
import { AuthProvider, useAuth } from './context/AuthContext';
import LoginPage from './pages/auth/LoginPage';
import AdminJDPanel from './pages/admin/AdminJDPanel';


const queryClient = new QueryClient();

// ----------------------------------------------------
// ProtectedRoute Component: Ensures login for access.
// ----------------------------------------------------
interface ProtectedRouteProps {
    element: React.ReactElement;
    allowedRoles?: ('user' | 'admin')[];
}

const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ element, allowedRoles }) => {
    const { isAuthenticated, userRole, isLoading } = useAuth();

    if (isLoading) {
        return <div>Loading authentication...</div>;
    }
    
    // 💥 THIS LOGIC ENSURES STARTING ON LOGIN PAGE IF NOT AUTHENTICATED 💥
    if (!isAuthenticated) {
        return <Navigate to="/login" replace />;
    }

    if (allowedRoles && !allowedRoles.includes(userRole)) {
        // Redirection based on role for unauthorized attempts
        if (userRole === 'admin') {
            return <Navigate to="/admin/jds" replace />; 
        }
        return <Navigate to="/dashboard" replace />;
    }

    return element;
};

// ----------------------------------------------------
// App Component 
// ----------------------------------------------------
const App = () => (
    <QueryClientProvider client={queryClient}>
        <TooltipProvider>
            <Toaster />
            <Sonner />
            <BrowserRouter>
                <AuthProvider> 
                    <Layout>
                        <Routes>
                            
                            {/* ------------------- PUBLIC LOGIN ROUTE (STARTING POINT) ------------------- */}
                            <Route path="/login" element={<LoginPage />} />
                            
                            {/* Root path redirection: Immediately checked by ProtectedRoute */}
                            <Route 
                                path="/" 
                                element={<ProtectedRoute element={<RootRedirect />} />} 
                            />

                            {/* ------------------- PROTECTED ADMIN ONLY ROUTE ------------------- */}
                            <Route 
                                path="/admin/jds" 
                                element={<ProtectedRoute element={<AdminJDPanel />} allowedRoles={['admin']} />} 
                            />
                            
                            {/* ------------------- PROTECTED USER ONLY ROUTES ------------------- */}
                            <Route 
                                path="/dashboard" 
                                element={<ProtectedRoute element={<Dashboard />} allowedRoles={['user']} />} 
                            />
                            <Route 
                                path="/candidates/upload-resume" 
                                element={<ProtectedRoute element={<UploadResume />} allowedRoles={['user']} />} 
                            />
                            <Route 
                                path="/jobs/upload-jd" 
                                element={<ProtectedRoute element={<UploadJD />} allowedRoles={['user']} />} 
                            />
                            <Route path="/matching" element={<ProtectedRoute element={<Matching />} allowedRoles={['user']} />} />
                            <Route path="/skill-gap" element={<ProtectedRoute element={<SkillGap />} allowedRoles={['user']} />} />
                            <Route path="/assessments/create" element={<ProtectedRoute element={<CreateAssessment />} allowedRoles={['user']} />} />
                            <Route path="/interviews/questions" element={<ProtectedRoute element={<InterviewQuestions />} allowedRoles={['user']} />} />
                            <Route path="/interviews/results" element={<ProtectedRoute element={<InterviewResults />} allowedRoles={['user']} />} />

                            {/* Catch-all route */}
                            <Route path="*" element={<NotFound />} />

                        </Routes>
                    </Layout>
                </AuthProvider>
            </BrowserRouter>
        </TooltipProvider>
    </QueryClientProvider>
);

// Helper component for root redirection based on role
const RootRedirect = () => {
    const { userRole } = useAuth();

    if (userRole === 'admin') {
        return <Navigate to="/admin/jds" replace />;
    }
    // Default to user dashboard for regular user
    return <Navigate to="/dashboard" replace />;
}

export default App;