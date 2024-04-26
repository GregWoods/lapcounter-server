import './EditDriverName.css'
import { useEffect } from 'react';


function EditDriverName({ showMe, focusMe, driverIdx, driverName, setDriverName}) {
    const driverNumber = driverIdx + 1;
    const driverCssClass = "driver" + driverNumber;
    const containerCssClass = driverCssClass + " EditDriverName"
    const id = "txtDriverName" + driverNumber;

    useEffect(() => {
        if (showMe && focusMe) {
            console.log("useEffect");
            const input = document.getElementById(id);
            input.focus();
            input.select();
        }
    });

    return (
        <div data-driver-number={driverNumber} className={containerCssClass}>
            <span className="driverNumber emphasized">{driverNumber}</span>
            <input type="text" data-driver-number={driverNumber} 
                className={driverCssClass} 
                id={id}
                onChange={evt => setDriverName(evt.target.value)} 
                onClick={(e) => { e.target.select(); console.log("onClick"); }}
                defaultValue={driverName} />
        </div>
    );
}

export default EditDriverName;
