import { BrowserRouter, Routes, Route, Link, createBrowserRouter } from 'react-router-dom';
import App from './App.jsx'
import NextRace from './components/NextRace/NextRace.jsx'

// https://reactrouter.com/start/modes  - using Data mode
const router = createBrowserRouter([
    {
        path: "/",
        element: <App />,
        /*loader: async () => {
            const response = await fetch('/api/home');
            return response.json();
        },*/
    } ,{
        path: "nextrace",
        element: <NextRace />,
        loader: async () => {
            const url = `${import.meta.env.VITE_API_URL}/drivers/nextrace/`;
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

