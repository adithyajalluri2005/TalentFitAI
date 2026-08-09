import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const TOKEN_KEY = 'authToken';
const ROLE_KEY = 'userRole';
const USERNAME_KEY = 'username';

// ----------------------------------------------------
// 1. Types Definition
// ----------------------------------------------------
type UserRole = 'user' | 'admin' | null;

interface AuthContextType {
    /** Whether the user is currently logged in. */
    isAuthenticated: boolean;
    /** The role of the logged-in user ('user', 'admin', or null if logged out). */
    userRole: UserRole;
    /** The logged-in user's name, or null. */
    username: string | null;
    /** Whether the context is currently loading (e.g., validating a stored token). */
    isLoading: boolean;
    /** Authenticates against the backend. Throws with a message on failure. */
    login: (username: string, password: string) => Promise<void>;
    /** Function to log out the current user. */
    logout: () => void;
}

// ----------------------------------------------------
// 2. Context Initialization
// ----------------------------------------------------
const AuthContext = createContext<AuthContextType | undefined>(undefined);

/** Read the stored bearer token. Used by the axios interceptor in services/api.ts. */
export const getStoredToken = () => localStorage.getItem(TOKEN_KEY);

const clearSession = () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(ROLE_KEY);
    localStorage.removeItem(USERNAME_KEY);
};

// ----------------------------------------------------
// 3. Auth Provider Component
// ----------------------------------------------------
export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [isAuthenticated, setIsAuthenticated] = useState(false);
    const [userRole, setUserRole] = useState<UserRole>(null);
    const [username, setUsername] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const navigate = useNavigate();

    const logout = useCallback(() => {
        clearSession();
        setUserRole(null);
        setUsername(null);
        setIsAuthenticated(false);
        navigate('/login');
    }, [navigate]);

    // Validate any stored token against the backend on mount. A token in
    // localStorage is not proof of anything -- it may be expired, or forged --
    // so the server decides.
    useEffect(() => {
        const token = localStorage.getItem(TOKEN_KEY);
        if (!token) {
            setIsLoading(false);
            return;
        }

        let cancelled = false;
        axios
            .get(`${API_BASE_URL}/auth/me`, {
                headers: { Authorization: `Bearer ${token}` },
                timeout: 90000, // free-tier backends cold-start slowly
            })
            .then((res) => {
                if (cancelled) return;
                setUserRole(res.data.role);
                setUsername(res.data.username);
                setIsAuthenticated(true);
                localStorage.setItem(ROLE_KEY, res.data.role);
                localStorage.setItem(USERNAME_KEY, res.data.username);
            })
            .catch((err) => {
                if (cancelled) return;
                // Only drop the session when the server actively rejects the
                // token. A network blip or a sleeping backend must not log the
                // user out.
                if (err?.response?.status === 401) {
                    clearSession();
                    setUserRole(null);
                    setUsername(null);
                    setIsAuthenticated(false);
                }
            })
            .finally(() => {
                if (!cancelled) setIsLoading(false);
            });

        return () => {
            cancelled = true;
        };
    }, []);

    // Log out when any API call reports the token is no longer valid.
    useEffect(() => {
        const onUnauthorized = () => logout();
        window.addEventListener('auth:unauthorized', onUnauthorized);
        return () => window.removeEventListener('auth:unauthorized', onUnauthorized);
    }, [logout]);

    /**
     * Authenticates against POST /auth/login, stores the returned JWT, and
     * redirects based on the role the *server* assigned.
     */
    const login = async (user: string, password: string) => {
        try {
            const res = await axios.post(
                `${API_BASE_URL}/auth/login`,
                { username: user, password },
                { timeout: 90000 },
            );

            const { access_token, role, username: name } = res.data;

            localStorage.setItem(TOKEN_KEY, access_token);
            localStorage.setItem(ROLE_KEY, role);
            localStorage.setItem(USERNAME_KEY, name);

            setUserRole(role);
            setUsername(name);
            setIsAuthenticated(true);

            navigate(role === 'admin' ? '/admin/jds' : '/dashboard');
        } catch (err: any) {
            if (err?.response?.status === 401) {
                throw new Error('Invalid username or password.');
            }
            if (err?.code === 'ECONNABORTED') {
                throw new Error('The server took too long to respond. It may be waking up — try again.');
            }
            throw new Error(
                err?.response?.data?.detail || 'Could not reach the server. Please try again.',
            );
        }
    };

    return (
        <AuthContext.Provider
            value={{ isAuthenticated, userRole, username, isLoading, login, logout }}
        >
            {children}
        </AuthContext.Provider>
    );
};

// ----------------------------------------------------
// 4. Custom Hook for Consumption
// ----------------------------------------------------
export const useAuth = () => {
    const context = useContext(AuthContext);
    if (context === undefined) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
};
