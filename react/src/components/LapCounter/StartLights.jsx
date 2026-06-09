import { useState, useEffect, useRef } from 'react';
import ReactModal from 'react-modal';


const LIGHTS_OFF_COLOR = "#222";
const LIGHTS_ON_COLOR = "#F22";
const initialLightsState = [LIGHTS_OFF_COLOR, LIGHTS_OFF_COLOR, LIGHTS_OFF_COLOR, LIGHTS_OFF_COLOR, LIGHTS_OFF_COLOR];
const allLightsOn = [LIGHTS_ON_COLOR, LIGHTS_ON_COLOR, LIGHTS_ON_COLOR, LIGHTS_ON_COLOR, LIGHTS_ON_COLOR];

// lightsOut is controlled by the parent (set true when lapdata publishes Running state).
// The browser countdown animation is cosmetic only — lapdata owns the actual lights-out moment.
const StartLights = ({showMe, onClose, lightsOut}) => {

    const [startLightValues, setStartLightValues] = useState(initialLightsState);
    const longBeepRef = useRef(null);

    function setLightOn(lightNumber, shortBeep) {
        shortBeep.play();
        const newLightValues = initialLightsState.map((_, index) =>
            index <= lightNumber - 1 ? LIGHTS_ON_COLOR : LIGHTS_OFF_COLOR
        );
        setStartLightValues(newLightValues);
    }

    const startCountdown = () => {
        console.log("start lights");

        const shortBeep = new Audio('sounds/Beep.wav');
        shortBeep.setAttribute("crossOrigin", "anonymous");
        setTimeout(() => { shortBeep.volume = 1; }, 0);

        const longBeep = new Audio('sounds/LongBeep.wav');
        longBeep.setAttribute("crossOrigin", "anonymous");
        setTimeout(() => { longBeep.volume = 1; }, 0);
        longBeepRef.current = longBeep;

        // Lights go on 1..5 — lapdata controls the lights-out moment via race_state Running
        setTimeout(() => { setLightOn(1, shortBeep) }, 2000);
        setTimeout(() => { setLightOn(2, shortBeep) }, 3000);
        setTimeout(() => { setLightOn(3, shortBeep) }, 4000);
        setTimeout(() => { setLightOn(4, shortBeep) }, 5000);
        setTimeout(() => { setLightOn(5, shortBeep) }, 6000);
    };

    // Triggered when lapdata publishes state: "Running" — lights out, race go!
    useEffect(() => {
        if (!lightsOut || !showMe) return;
        // Force all 5 on (handles edge case where Running arrives before countdown finishes)
        setStartLightValues(allLightsOn);
        const t = setTimeout(() => {
            longBeepRef.current?.play();
            setStartLightValues(initialLightsState);
            setTimeout(() => onClose(), 1000);
        }, 300);
        return () => clearTimeout(t);
    }, [lightsOut]); // eslint-disable-line react-hooks/exhaustive-deps

    return (
        <ReactModal
            isOpen={showMe}
            contentLabel="Start Lights"
            closeTimeoutMS={400}
            className="ReactModalContent"
            overlayClassName="ReactModalOverlay"
            onAfterOpen={() => startCountdown()}
            shouldCloseOnOverlayClick={false}
            shouldCloseOnEsc={false}
            style={{content: { backgroundColor: 'rgba(0,0,0,0.0)' }}}
            ariaHideApp={false}
        >
            <svg className="trafficlights" width="100%" viewBox="0 0 500 100">
                <rect width="500" height="100" rx="20" ry="20" style={{fill:'#111', strokeWidth:3, stroke:'#000'}} />
                <circle cx="53"  cy="50" r="30" stroke="black" strokeWidth="2" fill={startLightValues[0]} id="tl_red1"/>
                <circle cx="151" cy="50" r="30" stroke="black" strokeWidth="2" fill={startLightValues[1]} id="tl_red2"/>
                <circle cx="249" cy="50" r="30" stroke="black" strokeWidth="2" fill={startLightValues[2]} id="tl_red3"/>
                <circle cx="347" cy="50" r="30" stroke="black" strokeWidth="2" fill={startLightValues[3]} id="tl_red4"/>
                <circle cx="445" cy="50" r="30" stroke="black" strokeWidth="2" fill={startLightValues[4]} id="tl_red5"/>
            </svg>
        </ReactModal>
    );
}

export default StartLights;
