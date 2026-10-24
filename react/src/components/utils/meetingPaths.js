import { useParams } from 'react-router-dom';

// Guest pages live under /m/<public_id>/..., so their links must stay inside that prefix.
// Outside it (the admin pages) the base is empty and "home" is the admin home at "/".
export function useGuestBase() {
    const { publicId } = useParams();
    return publicId ? `/m/${publicId}` : '';
}
