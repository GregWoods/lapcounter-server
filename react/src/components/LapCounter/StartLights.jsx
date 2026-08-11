import { useEffect, useRef } from 'react';
import ReactModal from 'react-modal';


const LIGHTS_OFF_COLOR = "#222";
const LIGHTS_ON_COLOR = "#F22";

// Pure renderer. lapdata owns the whole start-light sequence and publishes it in
// race_state: `start_lights` (0-5 lit) as each light comes on, then the lights-out
// moment as the state -> Running transition (`lightsOut`). This component just
// reflects those, so every client renders identical, in-sync lights with no local
// countdown clock to drift.
const StartLights = ({ showMe, onClose, lightsOut, startLights = 0 }) => {
    const shortBeepRef = useRef(null);
    const longBeepRef = useRef(null);
    const prevLightsRef = useRef(0);

    // Prime the audio when the modal opens (also acts as the per-open reset point).
    useEffect(() => {
        if (!showMe) return;
        shortBeepRef.current = new Audio('sounds/Beep.wav');
        longBeepRef.current = new Audio('sounds/LongBeep.wav');
        prevLightsRef.current = 0;
    }, [showMe]);

    // Short beep each time lapdata lights another light.
    useEffect(() => {
        if (!showMe) return;
        if (startLights > prevLightsRef.current) {
            shortBeepRef.current?.play().catch(() => {});
        }
        prevLightsRef.current = startLights;
    }, [startLights, showMe]);

    // Lights out (lapdata published Running): long beep, then close the modal.
    useEffect(() => {
        if (!lightsOut || !showMe) return;
        longBeepRef.current?.play().catch(() => {});
        const t = setTimeout(() => onClose(), 1300);
        return () => clearTimeout(t);
    }, [lightsOut]); // eslint-disable-line react-hooks/exhaustive-deps

    // All lights extinguish the instant the race goes (Running), F1-style.
    const lit = lightsOut ? 0 : startLights;
    const fill = i => (i < lit ? LIGHTS_ON_COLOR : LIGHTS_OFF_COLOR);

    return (
        <ReactModal
            isOpen={showMe}
            contentLabel="Start Lights"
            closeTimeoutMS={400}
            className="ReactModalContent"
            overlayClassName="ReactModalOverlay"
            shouldCloseOnOverlayClick={false}
            shouldCloseOnEsc={false}
            style={{content: { backgroundColor: 'rgba(0,0,0,0.0)' }}}
            ariaHideApp={false}
        >
            <svg className="trafficlights" width="100%" viewBox="0 0 500 100">
                <rect width="500" height="100" rx="20" ry="20" style={{fill:'#111', strokeWidth:3, stroke:'#000'}} />
                <circle cx="53"  cy="50" r="30" stroke="black" strokeWidth="2" fill={fill(0)} id="tl_red1"/>
                <circle cx="151" cy="50" r="30" stroke="black" strokeWidth="2" fill={fill(1)} id="tl_red2"/>
                <circle cx="249" cy="50" r="30" stroke="black" strokeWidth="2" fill={fill(2)} id="tl_red3"/>
                <circle cx="347" cy="50" r="30" stroke="black" strokeWidth="2" fill={fill(3)} id="tl_red4"/>
                <circle cx="445" cy="50" r="30" stroke="black" strokeWidth="2" fill={fill(4)} id="tl_red5"/>
            </svg>
        </ReactModal>
    );
}

export default StartLights;
