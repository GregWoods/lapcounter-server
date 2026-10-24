import { Timer, Trophy } from 'lucide-react';

const LABELS = { Points: 'Finishing Position', FastestLap: 'Fastest Lap', Championship: 'Championship' };

// Fastest Lap → stopwatch; Finishing Position (and anything else) → trophy.
export default function SessionTypeIcon({ type }) {
    return (
        <span className="admin-session-icon" title={LABELS[type] || type}>
            {type === 'FastestLap' ? <Timer size={26} /> : <Trophy size={26} />}
        </span>
    );
}
