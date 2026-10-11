import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate, useParams } from "react-router-dom";
import Layout from "./components/Layout";
import Start from "./pages/coach/Start";
import Session from "./pages/coach/Session";
import Progress from "./pages/coach/Progress";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient();

function SessionRedirect() {
    const { threadId } = useParams();
    return <Navigate to={`/session/${threadId}/plan`} replace />;
}

// There is no login: a random candidate id in localStorage ties a browser's
// coaching sessions together (see services/coach.ts).
const App = () => (
    <QueryClientProvider client={queryClient}>
        <TooltipProvider>
            <Toaster />
            <Sonner />
            <BrowserRouter>
                <Layout>
                    <Routes>
                        <Route path="/" element={<Navigate to="/dashboard" replace />} />
                        <Route path="/dashboard" element={<Progress />} />
                        <Route path="/start" element={<Start />} />
                        <Route path="/session/:threadId" element={<SessionRedirect />} />
                        <Route path="/session/:threadId/:tab" element={<Session />} />
                        <Route path="*" element={<NotFound />} />
                    </Routes>
                </Layout>
            </BrowserRouter>
        </TooltipProvider>
    </QueryClientProvider>
);

export default App;
