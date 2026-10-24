import {useState, useEffect} from 'react';
import './YellowFlag.css';



// Smooth tenths for the grace countdown. lapdata sends whole seconds; between messages we
// count down using only time elapsed since the last one arrived (performance.now()), never
// a deadline against this screen's wall clock, so every display still agrees. Clamped to
// stay above the next whole second so a late message can't make it dip early.
const useTenthsLeft = (secondsLeft) => {
    const [tenths, setTenths] = useState(secondsLeft);
    useEffect(() => {
        if (secondsLeft == null) return;
        const arrived = performance.now();
        const update = () => {
            const elapsed = (performance.now() - arrived) / 1000;
            setTenths(Math.max(secondsLeft - 1, secondsLeft - elapsed, 0));
        };
        update();
        const id = setInterval(update, 50);
        return () => clearInterval(id);
    }, [secondsLeft]);
    // The first render after secondsLeft appears runs before the effect has set `tenths`.
    return secondsLeft == null ? null : (tenths ?? secondsLeft);
};


// One full-width, vertically centred yellow bar for the whole yellow flag. During the grace
// period (secondsLeft set) it carries the countdown in tenths; once the power is cut
// (secondsLeft null) it says the race is paused and the whole screen flashes yellow behind
// it. Clearing the flag is done from RaceControl.
const YellowFlagRacePaused = ({showMe, secondsLeft}) => {
    const tenthsLeft = useTenthsLeft(secondsLeft);
    if (!showMe) return null;

    const paused = tenthsLeft == null;
    return (
        <div id="yellowbarwrap">
            {paused && <div id="yellowflash" />}
            <div id="yellowbar">
                {paused ? 'RACE PAUSED' : tenthsLeft.toFixed(1)}
            </div>
        </div>
    );
}

export default YellowFlagRacePaused;
