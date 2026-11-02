import { useEffect, useState } from 'react';
import { ArrowLeft, X } from 'lucide-react';
import { API_URL } from '../../endpoints.js';
import { onCarImgError } from './carImages.js';
import './CarPicker.css';

// Lane colours (the `lanes` table's CSS names) that need dark text on them.
const LIGHT_LANE_COLORS = new Set(['yellow', 'orange', 'white']);


// Full-screen picker for the car on one lane: RaceControl's Edit Cars (step 2) and
// NextRace's car thumbnails. Either way the car goes on the lane for the rest of the
// session (#111). Sized in em from its own clamp(), not the TV page's rem, so it works on a
// phone. `onBack` is optional: NextRace opens straight onto this step.
//
// A car already on another lane this session wears that lane's colour. It can still be
// picked, since one car briefly on two lanes is how a swap between lanes goes, but no real
// car can race on two IDs, so it shouldn't happen by accident.
export default function CarPicker({ lane, laneColor, currentCarId, onPick, onBack, onClose }) {
    const [cars, setCars] = useState([]);
    const [otherLanes, setOtherLanes] = useState([]);

    useEffect(() => {
        fetch(`${API_URL}/api/cars`)
            .then(res => res.ok ? res.json() : [])
            .then(setCars, () => setCars([]));
        // Disabled lanes are left out: a car on an ID that isn't racing is free to move.
        fetch(`${API_URL}/sessions/active/cars`)
            .then(res => res.ok ? res.json() : { lanes: [] })
            .then(data => setOtherLanes(data.lanes.filter(l => l.lane !== lane && l.lane_enabled && l.car_id != null)),
                () => setOtherLanes([]));
    }, [lane]);

    useEffect(() => {
        const onKeyDown = (e) => { if (e.key === 'Escape') onClose(); };
        window.addEventListener('keydown', onKeyDown);
        return () => window.removeEventListener('keydown', onKeyDown);
    }, [onClose]);

    // How a car is marked: this lane's car first, else the first other lane using it.
    const marking = (car) => {
        if (car.id === currentCarId) {
            return { className: 'carpicker-car--current', color: laneColor, label: 'Current car' };
        }
        const usedOn = otherLanes.filter(l => l.car_id === car.id);
        if (!usedOn.length) return null;
        return {
            className: 'carpicker-car--in-use',
            color: usedOn[0].lane_color,
            label: `On lane ${usedOn.map(l => l.lane).join(' & ')}`,
        };
    };

    return (
        <div className="carpicker">
            <header className="carpicker-header">
                {onBack ? (
                    <button className="carpicker-icon" onClick={onBack} aria-label="Back"><ArrowLeft /></button>
                ) : <span className="carpicker-icon-spacer" />}
                <h2>
                    <span
                        className={`carpicker-lane${LIGHT_LANE_COLORS.has(laneColor) ? ' carpicker--light' : ''}`}
                        style={{ '--lane-color': laneColor }}
                    >Lane {lane}</span>
                    {' '}choose a car
                </h2>
                <button className="carpicker-icon" onClick={onClose} aria-label="Close"><X /></button>
            </header>
            <div className="carpicker-grid">
                {cars.map((car) => {
                    const mark = marking(car);
                    return (
                        <button
                            key={car.id}
                            className={`carpicker-car${mark ? ` ${mark.className}` : ''}${mark && LIGHT_LANE_COLORS.has(mark.color) ? ' carpicker--light' : ''}`}
                            style={mark ? { '--lane-color': mark.color } : undefined}
                            onClick={() => onPick(car)}
                        >
                            <img src={car.url} alt={car.name ?? 'Car'} onError={onCarImgError} />
                            {mark && <span className="carpicker-car-label">{mark.label}</span>}
                        </button>
                    );
                })}
            </div>
        </div>
    );
}
