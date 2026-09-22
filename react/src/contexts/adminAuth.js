import { createContext, useContext } from 'react';

// Kept apart from AdminAuthContext.jsx so that file exports only a component, which
// Vite's fast refresh needs in order to hot-reload it.
export const AdminAuthContext = createContext(null);

export function useAdminAuth() {
    return useContext(AdminAuthContext);
}
