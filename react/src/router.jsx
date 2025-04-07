import { createBrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import NextRace from './NextRace.jsx'

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
            const response = await fetch(`${import.meta.env.VITE_API_URL}/drivers/nextrace/`);
            if (!response.ok) {
                throw new Error('Failed to load drivers data');
            }
            return response.json();
        },
    },
]);

export default router;
