import { createBrowserRouter, redirect } from 'react-router-dom';
import App from './App.jsx'
import NextRace from './components/NextRace/NextRace.jsx'
import Results from './components/Results/Results.jsx'
import Register from './components/Register/Register.jsx'
import Meetings from './components/Admin/Meetings.jsx'
import Sessions from './components/Admin/Sessions.jsx'
import Drivers from './components/Drivers/Drivers.jsx'
import RaceControl from './components/RaceControl/RaceControl.jsx'
import MeetingLayout from './components/Meeting/MeetingLayout.jsx'
import MeetingHome from './components/Meeting/MeetingHome.jsx'
import RequireAdmin from './components/RequireAdmin/RequireAdmin.jsx'
import { API_URL } from './endpoints.js';

// Loader for a legacy top-level path: forward to the same page under the active meeting,
// or to the admin home when no meeting is active.
function redirectToActive(path) {
    return {
        path,
        loader: async ({ params }) => {
            let meeting = null;
            try {
                const res = await fetch(`${API_URL}/meetings/active`);
                if (res.ok) meeting = await res.json();
            } catch { /* fall through to "/" */ }
            if (!meeting) return redirect("/");
            const rest = path.replace(":sessionId", params.sessionId ?? "");
            return redirect(`/m/${meeting.public_id}/${rest}`);
        },
    };
}

// https://reactrouter.com/start/modes  - using Data mode
const router = createBrowserRouter([
    {
        path: "/",
        element: <RequireAdmin><Meetings /></RequireAdmin>,
        loader: async () => {
            try {
                const [meetingsRes, activeRes] = await Promise.all([
                    fetch(`${API_URL}/meetings`),
                    fetch(`${API_URL}/meetings/active`),
                ]);
                if (!meetingsRes.ok) return { meetings: [], activeMeetingId: null };
                const activeMeetingId = activeRes.ok ? (await activeRes.json()).id : null;
                return { meetings: await meetingsRes.json(), activeMeetingId };
            } catch {
                return { meetings: [], activeMeetingId: null };
            }
        },
    },
    {
        // Everything a driver sees lives under their meeting's unguessable id.
        id: "meeting",
        path: "m/:publicId",
        element: <MeetingLayout />,
        loader: async ({ params }) => {
            try {
                const res = await fetch(`${API_URL}/meetings/by-public-id/${params.publicId}`);
                return res.ok ? res.json() : null;
            } catch {
                return null;
            }
        },
        children: [
            { index: true, element: <MeetingHome /> },
            {
                path: "sessions",
                element: <RequireAdmin><Sessions /></RequireAdmin>,
                loader: async ({ params }) => {
                    try {
                        const m = await fetch(`${API_URL}/meetings/by-public-id/${params.publicId}`);
                        if (!m.ok) return [];
                        const res = await fetch(`${API_URL}/sessions?meeting_id=${(await m.json()).id}`);
                        return res.ok ? res.json() : [];
                    } catch {
                        return [];
                    }
                },
            },
            { path: "racecontrol", element: <RequireAdmin><RaceControl /></RequireAdmin> },
        {
            path: "currentrace",
            element: <App />,
            loader: async () => {
                try {
                    // The DB is authoritative for which race is current (Running else pending).
                    const res = await fetch(`${API_URL}/races/current/`);
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
                try {
                    const res = await fetch(`${API_URL}/races/pending/`);
                    if (!res.ok) {
                        const body = await res.json().catch(() => ({}));
                        // A 404 means "no race queued", which is NOT the same as "session over":
                        // a running session whose queue was never generated (sample data) or was
                        // emptied looks identical here. regen-status is what tells them apart.
                        const regen = await fetch(`${API_URL}/sessions/active/regen-status`)
                            .then(r => r.ok ? r.json() : null)
                            .catch(() => null);
                        return {
                            error: body.detail || 'No pending race available',
                            activeSessionId: regen?.session_id ?? null,
                        };
                    }
                    return res.json();
                } catch {
                    return { error: 'Could not reach the server' };
                }
            },
        },
        {
            path: "results",
            element: <Results />,
            loader: async () => {
                try {
                    const res = await fetch(`${API_URL}/sessions/current/results`);
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
                    const res = await fetch(`${API_URL}/sessions/${params.sessionId}/results`);
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
        },
        ],
    },
    // The old top-level guest URLs (bookmarks, TV browsers) go to the active meeting's page.
    redirectToActive("currentrace"),
    redirectToActive("nextrace"),
    redirectToActive("results"),
    redirectToActive("results/:sessionId"),
    redirectToActive("register"),
    redirectToActive("racecontrol"),
    {
        path: "drivers",
        element: <RequireAdmin><Drivers /></RequireAdmin>,
        loader: async () => {
            try {
                const res = await fetch(`${API_URL}/drivers/`);
                if (!res.ok) return [];
                return res.json();
            } catch {
                return [];
            }
        },
    },
    // Sessions moved under their meeting; the old combined page is gone.
    { path: "meetings", loader: () => redirect("/") },
]);

export default router;
