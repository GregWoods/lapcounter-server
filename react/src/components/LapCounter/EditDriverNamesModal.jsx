import EditDriverName from './EditDriverName';
import ReactModal from 'react-modal';


const EditDriverNamesModal = ({ showMe, onClose, drivers, setDrivers, driverIdxToFocus }) => {
    
    const initialDrivers = drivers.map(d => d.name);
    const newDrivers = [...drivers];

    function changeDriverName(idx, newName) {
        if (newName === '') {   
            newName = '\u00A0';
        }
        newDrivers[idx] = {...drivers[idx], name: newName ?? '\u00A0'}; //nbsp inserted to maintain height
    }

    function onSaveAndClose() {
        setDrivers(newDrivers);
        onClose();
    }

    return (
        <ReactModal
            isOpen={showMe}
            onRequestClose={onClose}
            id="editdriversmodal"
            contentLabel="Edit Driver Names"
            closeTimeoutMS={400}
            className="ReactModalContent"
            overlayClassName="ReactModalOverlay"
            ariaHideApp={false}
        >
            <h2 className="header">Edit Driver Names</h2>
            <form onSubmit={evt => evt.preventDefault() }>
                {initialDrivers.map(function(driverName, idx) {
                    return <EditDriverName 
                                key={idx}
                                driverIdx={idx} 
                                driverName={driverName} 
                                setDriverName={(name) => {changeDriverName(idx, name)}} 
                                showMe={showMe}
                                focusMe={(driverIdxToFocus === idx)}
                                />
                })}
            
                <h2><button onClick={onSaveAndClose}>Close</button></h2>
            </form>
        </ReactModal>
    );
}

export default EditDriverNamesModal;