import { createBrowserRouter } from 'react-router-dom';
import App from './App.jsx'
import NextRace from './components/NextRace/NextRace.jsx'
import Home from './components/Home/Home.jsx'
import Results from './components/Results/Results.jsx'
import Register from './components/Register/Register.jsx'
import Admin from './components/Admin/Admin.jsx'
import Drivers from './components/Drivers/Drivers.jsx'
import PinPrompt from './components/PinPrompt/PinPrompt.jsx'
import { useAdminAuth } from './contexts/AdminAuthContext.jsx'

function RequireAdmin({ children }) {
    const { isAdmin } = useAdminAuth();
    return isAdmin ? children : <PinPrompt />;
}

// https://reactrouter.com/start/modes  - using Data mode
const router = createBrowserRouter([
    {
        path: "/",
        element: <Home />,
        loader: async () => {
            try {
                const res = await fetch(`${import.meta.env.VITE_API_URL}/meetings/active`);
                if (!res.ok) return null;
                return res.json();
            } catch {
                return null;
            }
        },
    },
    {
        path: "currentrace",
        element: <App />,
        loader: async () => {
            try {
                const res = await fetch(`${import.meta.env.VITE_API_URL}/races/pending/`);
                if (!res.ok) return null;
                return res.json();
            } catch {
                return null;
            }
        },
    },
    {
        path: "nextrace",
        element: <NextRace />,
        loader: async () => {
            const res = await fetch(`${import.meta.env.VITE_API_URL}/races/pending/`);
            if (!res.ok) throw new Error('Failed to load pending race');
            return res.json();
        },
    },
    {
        path: "results",
        element: <Results />,
        loader: async () => {
            try {
                const res = await fetch(`${import.meta.env.VITE_API_URL}/sessions/active/results`);
                if (!res.ok) return { races: [], drivers: [] };
                return res.json();
            } catch {
                return { races: [], drivers: [] };
            }
        },
    },
    {
        path: "results/:sessionId",
        element: <Results />,
        loader: async ({ params }) => {
            try {
                const res = await fetch(`${import.meta.env.VITE_API_URL}/sessions/${params.sessionId}/results`);
                if (!res.ok) return { races: [], drivers: [] };
                return res.json();
            } catch {
                return { races: [], drivers: [] };
            }
        },
    },
    {
        path: "register",
        element: <Register />,
        loader: async () => {
            try {
                const res = await fetch(`${import.meta.env.VITE_API_URL}/meetings/upcoming`);
                if (!res.ok) return [];
                return res.json();
            } catch {
                return [];
            }
        },
    },
    {
        path: "drivers",
        element: <RequireAdmin><Drivers /></RequireAdmin>,
        loader: async () => {
            try {
                const res = await fetch(`${import.meta.env.VITE_API_URL}/drivers/`);
                if (!res.ok) return [];
                return res.json();
            } catch {
                return [];
            }
        },
    },
    {
        path: "meetings",
        element: <RequireAdmin><Admin /></RequireAdmin>,
        loader: async () => {
            try {
                const [meetingsRes, activeRes] = await Promise.all([
                    fetch(`${import.meta.env.VITE_API_URL}/meetings`),
                    fetch(`${import.meta.env.VITE_API_URL}/meetings/active`),
                ]);
                if (!meetingsRes.ok) return { meetings: [], activeMeetingId: null };
                const meetings = await meetingsRes.json();
                const activeMeetingId = activeRes.ok ? (await activeRes.json()).id : null;
                const withSessions = await Promise.all(
                    meetings.map(async m => {
                        try {
                            const sr = await fetch(`${import.meta.env.VITE_API_URL}/sessions?meeting_id=${m.id}`);
                            return { ...m, sessions: sr.ok ? await sr.json() : [] };
                        } catch {
                            return { ...m, sessions: [] };
                        }
                    })
                );
                return { meetings: withSessions, activeMeetingId };
            } catch {
                return { meetings: [], activeMeetingId: null };
            }
        },
    },
]);

export default router;
