import React, { createContext, useContext, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

// ----------------------------------------------------
// 1. Types Definition
// ----------------------------------------------------
type UserRole = 'user' | 'admin' | null;

interface AuthContextType {
    /** Whether the user is currently logged in. */
    isAuthenticated: boolean;
    /** The role of the logged-in user ('user', 'admin', or null if logged out). */
    userRole: UserRole;
    /** Whether the context is currently loading (e.g., checking initial session). */
    isLoading: boolean;
    /** Function to log in a user and set their role. */
    login: (role: 'user' | 'admin') => void;
    /** Function to log out the current user. */
    logout: () => void;
}

// ----------------------------------------------------
// 2. Context Initialization
// ----------------------------------------------------
const AuthContext = createContext<AuthContextType | undefined>(undefined);

// ----------------------------------------------------
// 3. Auth Provider Component
// ----------------------------------------------------
export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [isAuthenticated, setIsAuthenticated] = useState(false);
    const [userRole, setUserRole] = useState<UserRole>(null);
    const [isLoading, setIsLoading] = useState(true);
    const navigate = useNavigate();

    // Check for stored session on initial mount
    useEffect(() => {
        const storedRole = localStorage.getItem('userRole') as UserRole;
        if (storedRole) {
            setUserRole(storedRole);
            setIsAuthenticated(true);
        }
        setIsLoading(false);
    }, []);

    /**
     * Simulates a login process, sets the user's role in state and local storage,
     * and redirects to the dashboard.
     * @param role - The role to assign ('user' for regular flow, 'admin' for panel access).
     */
    const login = (role: 'user' | 'admin') => {
        // NOTE: In a real app, this is where you'd handle the response from your backend's /login endpoint.
        
        // 1. Store the user's role (instead of a token, for this simple example)
        localStorage.setItem('userRole', role);
        
        // 2. Update state
        setUserRole(role);
        setIsAuthenticated(true);
        
        // 3. Redirect the user
        navigate('/dashboard'); 
    };

    /**
     * Clears the user session and redirects to the login page.
     */
    const logout = () => {
        // 1. Clear stored session data
        localStorage.removeItem('userRole');
        
        // 2. Update state
        setUserRole(null);
        setIsAuthenticated(false);
        
        // 3. Redirect the user
        navigate('/login');
    };

    return (
        <AuthContext.Provider value={{ isAuthenticated, userRole, isLoading, login, logout }}>
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