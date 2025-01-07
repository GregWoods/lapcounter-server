import { useState } from 'react';
import ReactModal from 'react-modal';


const LIGHTS_OFF_COLOR = "#222";
const LIGHTS_ON_COLOR = "#F22";
const initialLightsState = [LIGHTS_OFF_COLOR, LIGHTS_OFF_COLOR, LIGHTS_OFF_COLOR, LIGHTS_OFF_COLOR, LIGHTS_OFF_COLOR];

const StartLights = ({showMe, onClose, onLightsOut}) => {

    const [startLightValues, setStartLightValues] = useState(initialLightsState)

    function setLightOn (lightNumber, shortBeep) {
        shortBeep.play();
        //we generate the current light values from scratch, without regard for previous state
        //  because setting state in a setInterval doesn't work as you might expect.
        //  see: https://www.geeksforgeeks.org/accessing-state-in-settimeout-react-js/
        const newLightValues = initialLightsState.map((startLightValue, index) => {
            return (index <= lightNumber-1)
                ? LIGHTS_ON_COLOR
                : LIGHTS_OFF_COLOR
        });
        setStartLightValues(newLightValues);
    }


    const startCountdown = () => {
        console.log("start lights");

        //cache the audio to avoid delay on first beep
        //  10 year old report may reveal why I need a setTimeout to change volume
        //  https://bugs.chromium.org/p/chromium/issues/detail?id=33023
        //  Still doesn't work. I suspect I need to use the events on the Audio objects
        var shortBeep = new Audio('sounds/Beep.wav');
        setTimeout(() => { shortBeep.volume = 0; }, 0 );
        //shortBeep.volume = 0.0;
        shortBeep.preload = 'auto';    
        //shortBeep.play();
        setTimeout(() => { shortBeep.volume = 1; }, 0 );

        var longBeep = new Audio('sounds/LongBeep.wav');
        //setTimeout(() => { longBeep.volume = 0; }, 0 );
        longBeep.preload = 'auto';
        //longBeep.play();
        setTimeout(() => { longBeep.volume = 1; }, 0 );


        //https://www.fia.com/sites/default/files/regulation/file/03__Recommended_light_signals.pdf
        setTimeout(() => {setLightOn(1, shortBeep)}, 2000);
        setTimeout(() => {setLightOn(2, shortBeep)}, 3000);
        setTimeout(() => {setLightOn(3, shortBeep)}, 4000);
        setTimeout(() => {setLightOn(4, shortBeep)}, 5000);
        setTimeout(() => {setLightOn(5, shortBeep)}, 6000);
        setTimeout(() => {
            onLightsOut();
            longBeep.play();    
            setStartLightValues(initialLightsState);
            setTimeout(() => {onClose();}, 1000)
        //lights go out between 200ms and 3000ms after the last light goes on
        }, 6000 + (Math.random() * 2800) + 200);
    };

    return (
        <ReactModal
            isOpen={showMe}
            onRequestClose={onClose}
            contentLabel="Start Lights"
            closeTimeoutMS={400}
            className="ReactModalContent"
            overlayClassName="ReactModalOverlay"
            onAfterOpen={() => startCountdown()}
            style={{content: { backgroundColor: 'rgba(0,0,0,0.0)' }}}
            ariaHideApp={false}
        >        
            <svg className="trafficlights" width="1000" height="200" viewBox="0, 0, 500, 100">
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
