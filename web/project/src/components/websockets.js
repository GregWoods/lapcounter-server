import { useEffect, useRef } from 'react';


const WebSockets = ({wsUrl, onIncomingMessage, debug}) => {

    const ws = useRef(null);

    useEffect(() => {
        if (debug) { console.log("!!! ws_CONNECT"); }
        ws.current = new WebSocket(wsUrl);
        ws.current.onopen = (evt) => ws_onOpen(evt);
        ws.current.onclose = (evt) => ws_onClose(evt);
        ws.current.onerror = (evt) => ws_onError(evt);

        const wsCurrent = ws.current;

        return () => {
            wsCurrent.close();
        };
    }, []);

    useEffect(() => {
        if (!ws.current) return;

        ws.current.onmessage = (evt) => {
            const message = JSON.parse(evt.data);
            if (message.type == 'lap') {
                onIncomingMessage(message);
            }
        };
    }, []);


    function ws_onOpen(e) {
        if (debug) { console.log("ws_onOpen()"); }
        if (debug) { console.log(e); }
    }

    function ws_onClose(e) {
        if (debug) { console.log("ws_onClose()"); }
        if (debug) { console.log(e); }
    }

    function ws_onError(e) {
        if (debug) { console.log("ws_onError()"); }
        if (debug) { console.log(e); }
    }

    // eslint-disable-next-line no-unused-vars
    function wsdisconnect() {
        if (debug) { console.log("wsdisconnect()"); }
        ws.close();
    }

    return null;
}

export default WebSockets;
