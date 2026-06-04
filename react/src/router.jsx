import { BrowserRouter, Routes, Route, Link, createBrowserRouter } from 'react-router-dom';
import App from './App.jsx'
import NextRace from './components/NextRace/NextRace.jsx'

// https://reactrouter.com/start/modes  - using Data mode
const router = createBrowserRouter([
    {
        path: "/",
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
    }, {
        path: "nextrace",
        element: <NextRace />,
        loader: async () => {
            const url = `${import.meta.env.VITE_API_URL}/races/pending/`;
            console.log('fetch driver data: ', url);
            const response = await fetch(url);
            if (!response.ok) {
                throw new Error('Failed to load drivers data');
            }
            return response.json();
        },
    },
]);

export default router;

