import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useAuth } from '../../context/AuthContext';
import { LogIn, Loader2 } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';

export default function LoginPage() {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [isLoading, setIsLoading] = useState(false);

    const { login } = useAuth();
    const { toast } = useToast();

    // The role is decided by the backend from the credentials -- there is no
    // client-side role selection, otherwise anyone could pick "admin".
    const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        if (!username.trim() || !password) {
            toast({
                title: 'Missing details',
                description: 'Enter both a username and a password.',
                variant: 'destructive',
            });
            return;
        }

        setIsLoading(true);
        try {
            await login(username.trim(), password);
            toast({
                title: 'Welcome back 👋',
                description: 'Signed in successfully.',
            });
        } catch (err: any) {
            toast({
                title: 'Sign-in failed',
                description: err?.message ?? 'Something went wrong. Please try again.',
                variant: 'destructive',
            });
            setPassword('');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="flex justify-center items-center min-h-screen bg-gray-50 dark:bg-gray-900 p-4">
            <Card className="w-full max-w-md shadow-2xl">
                <CardHeader className="space-y-1 text-center">
                    <CardTitle className="text-3xl font-bold flex justify-center items-center gap-2">
                        <LogIn className="w-6 h-6" />
                        TalentFitAI Login
                    </CardTitle>
                    <CardDescription>
                        Sign in to access the recruitment assistant platform.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <form onSubmit={handleSubmit} className="grid gap-6">
                        <div className="grid gap-2">
                            <Label htmlFor="username">Username</Label>
                            <Input
                                id="username"
                                type="text"
                                autoComplete="username"
                                value={username}
                                onChange={(e) => setUsername(e.target.value)}
                                disabled={isLoading}
                                autoFocus
                            />
                        </div>
                        <div className="grid gap-2">
                            <Label htmlFor="password">Password</Label>
                            <Input
                                id="password"
                                type="password"
                                autoComplete="current-password"
                                placeholder="••••••••"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                disabled={isLoading}
                            />
                        </div>

                        <Button type="submit" className="w-full h-12" disabled={isLoading}>
                            {isLoading ? (
                                <>
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                    Signing in…
                                </>
                            ) : (
                                <>
                                    <LogIn className="mr-2 h-4 w-4" />
                                    Sign In
                                </>
                            )}
                        </Button>

                        <p className="text-xs text-center text-muted-foreground">
                            The server may take up to a minute to wake up on the first
                            request.
                        </p>
                    </form>
                </CardContent>
            </Card>
        </div>
    );
}
