import PinPrompt from '../PinPrompt/PinPrompt.jsx';
import { useAdminAuth } from '../../contexts/adminAuth';

export default function RequireAdmin({ children }) {
    const { isAdmin } = useAdminAuth();
    return isAdmin ? children : <PinPrompt />;
}
