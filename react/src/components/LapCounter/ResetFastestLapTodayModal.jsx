import './ResetFastestLapTodayModal.css';
import ReactModal from 'react-modal';


const ResetFastestLapTodayModal = ({ showMe, onClose, resetFastestLapToday }) => 
{
    const onDone = () => {
        resetFastestLapToday();
        onClose();
    }
    const onCancel = () => {
        onClose();
    }
 
    return (
        <ReactModal
            isOpen={showMe}
            onRequestClose={onCancel}
            id="resetfastestlapsmodal"
            contentLabel="Reset Fastest Lap"
            closeTimeoutMS={400}
            className="ReactModalContent"
            overlayClassName="ReactModalOverlay" 
            ariaHideApp={false}
        >
            <form onSubmit={evt => evt.preventDefault() }>
                <h2>Reset Fastest Lap</h2>
        
                <p>Are you sure you want to reset today&apos;s fastest lap time?</p>

                <h2><button onClick={onCancel}>Cancel</button></h2>
                <h2><button onClick={onDone}>Reset</button></h2>
            </form>
        </ReactModal>
    );
}

export default ResetFastestLapTodayModal;