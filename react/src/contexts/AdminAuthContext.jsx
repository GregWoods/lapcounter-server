import { createContext, useContext, useState } from 'react';

const AdminAuthContext = createContext(null);

export function AdminAuthProvider({ children }) {
    const pinRequired = !!import.meta.env.VITE_ADMIN_PIN;
    const [isAdmin, setIsAdmin] = useState(
        () => !pinRequired || localStorage.getItem('adminAuth') === 'true'
    );

    const login = (pin) => {
        if (pin === import.meta.env.VITE_ADMIN_PIN) {
            setIsAdmin(true);
            localStorage.setItem('adminAuth', 'true');
            return true;
        }
        return false;
    };

    const logout = () => {
        setIsAdmin(false);
        localStorage.removeItem('adminAuth');
    };

    return (
        <AdminAuthContext.Provider value={{ isAdmin, login, logout }}>
            {children}
        </AdminAuthContext.Provider>
    );
}

export function useAdminAuth() {
    return useContext(AdminAuthContext);
}
