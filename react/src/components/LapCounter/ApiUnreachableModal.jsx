import ReactModal from 'react-modal';
import './ApiUnreachableModal.css';

// Shown whenever race_state.api_reachable is false. This is not a React-only
// progressive-enhancement concern: lapdata itself depends on the API for the pending
// race queue and persists race lifecycle through it, so an unreachable API means the
// whole system's source of truth is down — nothing on screen can be trusted while it's
// up. Unlike SoundBlockedModal this is never dismissable and never fades the background:
// there's nothing behind it worth preserving a view of, and it clears itself the instant
// lapdata's own next fetch succeeds (see _set_api_reachable in timestamps_to_lapdata.py).
const ApiUnreachableModal = ({ showMe }) => (
    <ReactModal
        isOpen={showMe}
        contentLabel="API Unreachable"
        className="apiUnreachableModal"
        overlayClassName="apiUnreachableModalOverlay"
        shouldCloseOnOverlayClick={false}
        shouldCloseOnEsc={false}
        ariaHideApp={false}
    >
        <div id="apiUnreachableContainer">
            <div id="apiUnreachableIcon">⚠️</div>
            <h1>Connection lost</h1>
            <p>Cannot reach the race server — waiting to reconnect…</p>
        </div>
    </ReactModal>
);

export default ApiUnreachableModal;
