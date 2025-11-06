import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
// Assuming AuthContext.tsx is in src/context/AuthContext.tsx and LoginPage is in src/pages/auth/
import { useAuth } from '../../context/AuthContext';import { LogIn, Users, UserCog, Loader2 } from 'lucide-react';
import { useToast } from '@/hooks/use-toast'; // Assuming you have a toast hook

export default function LoginPage() {
    // NOTE: For a real app, these would be user inputs tied to state
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    
    const { login } = useAuth();
    const { toast } = useToast();

    // ----------------------------------------------------
    // Dummy Authentication Logic
    // ----------------------------------------------------
    const handleLogin = async (role: 'user' | 'admin') => {
        setIsLoading(true);
        
        // --- Simulate Network Delay / API Call ---
        await new Promise(resolve => setTimeout(resolve, 800));

        // In a real application, you would check username/password against your backend
        // and receive a token and the user's role.
        
        // --- Simple Role-Based Validation (DUMMY) ---
        if (role === 'admin' && username === 'admin' && password === 'adminpass') {
            login('admin');
            toast({
                title: "Welcome Admin! 👋",
                description: "You have full access to JD management.",
            });
        } else if (role === 'user' && username === 'user' && password === 'userpass') {
            login('user');
            toast({
                title: "Welcome! 😊",
                description: "Starting your candidate assessment flow.",
            });
        } else {
            // Fallback for demo simplicity if credentials aren't checked
             if (role === 'admin' && !username.includes('admin')) {
                toast({
                    title: "Access Denied",
                    description: "Invalid admin credentials. (Try user: 'admin', pass: 'adminpass')",
                    variant: "destructive",
                });
            } else if (role === 'user' && !username.includes('user')) {
                 toast({
                    title: "Access Denied",
                    description: "Invalid user credentials. (Try user: 'user', pass: 'userpass')",
                    variant: "destructive",
                });
            } else {
                 toast({
                    title: "Access Denied",
                    description: "Invalid credentials.",
                    variant: "destructive",
                });
            }
        }

        setIsLoading(false);
    };

    // Handle form submission with Enter key
    const handleSubmit = (e: React.FormEvent<HTMLFormElement>, role: 'user' | 'admin') => {
        e.preventDefault();
        handleLogin(role);
    };

    return (
        <div className="flex justify-center items-center min-h-screen bg-gray-50 dark:bg-gray-900 p-4">
            <Card className="w-full max-w-lg shadow-2xl">
                <CardHeader className="space-y-1 text-center">
                    <CardTitle className="text-3xl font-bold flex justify-center items-center gap-2">
                        <LogIn className="w-6 h-6" />
                        TalentFitAI Login
                    </CardTitle>
                    <CardDescription>
                        Enter your credentials to access the recruitment assistant platform.
                    </CardDescription>
                </CardHeader>
                <CardContent className="grid gap-6">
                    <div className="grid gap-2">
                        <Label htmlFor="username">Username</Label>
                        <Input
                            id="username"
                            type="text"
                            placeholder="e.g., user or admin"
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            disabled={isLoading}
                        />
                    </div>
                    <div className="grid gap-2">
                        <Label htmlFor="password">Password</Label>
                        <Input
                            id="password"
                            type="password"
                            placeholder="••••••••"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            disabled={isLoading}
                        />
                    </div>

                    <div className="flex gap-4">
                        {/* User Login Button */}
                        <form onSubmit={(e) => handleSubmit(e, 'user')} className="flex-1">
                            <Button 
                                type="submit"
                                className="w-full h-12 bg-primary hover:bg-primary/90" 
                                disabled={isLoading}
                            >
                                {isLoading ? (
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                ) : (
                                    <Users className="mr-2 h-4 w-4" />
                                )}
                                Log In as User
                            </Button>
                        </form>
                        
                        {/* Admin Login Button */}
                        <form onSubmit={(e) => handleSubmit(e, 'admin')} className="flex-1">
                             <Button 
                                type="submit"
                                className="w-full h-12 bg-indigo-600 hover:bg-indigo-700 dark:bg-indigo-700 dark:hover:bg-indigo-800" 
                                disabled={isLoading}
                            >
                                {isLoading ? (
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin text-white" />
                                ) : (
                                    <UserCog className="mr-2 h-4 w-4" />
                                )}
                                Admin Access
                            </Button>
                        </form>
                    </div>

                </CardContent>
            </Card>
        </div>
    );
}