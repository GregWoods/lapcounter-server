import React from 'react';

const DriverCardTime = ({cssClass, label, lapTime}) => {
    const fltTime = parseFloat(lapTime);

    let displayTime;
    if (isNaN(fltTime)) {
        displayTime = "";
    } else if (fltTime > 99999) {
        // prevent off scale times from breaking the layout
        displayTime = "99999"
    } else if (fltTime < 100) {
        // the happy path... we never want more than 3dp
        displayTime = fltTime.toFixed(3);
    } else {
        // for larger number we limit to 5 significant figures
        displayTime = fltTime.toPrecision(5);
        
    }

    return (
        <div className={cssClass}>
            <div className="timelbl">{label}</div>
            <div className="time">&#8203;{displayTime}</div>
        </div>
    );
};

export default DriverCardTime;