// Where the API and MQTT broker are, worked out AT RUNTIME from the page's own address.
//
// They deliberately do NOT come from VITE_* env vars. Vite inlines those at BUILD time, so
// the published react image used to carry one hardcoded Pi address (192.168.8.3): the UI
// broke on any other address, and moving the stack to a different Pi meant a rebuild. The
// API and broker always run on the same host that served this page, so ask the browser.
//
// Consequence for the API: the browser's Origin is now whatever address the operator typed,
// so the API accepts any origin rather than one exact URL (see main.py's CORSMiddleware).
const host = window.location.hostname;

export const API_URL = `http://${host}:8000`;
export const MQTT_URL = `ws://${host}:8080`;

// Still a build-time value: it is a path on the API, not an address.
export const CAR_MEDIA_FOLDER = import.meta.env.VITE_CAR_MEDIA_FOLDER ?? 'media/cars';
export const CAR_MEDIA_URL = `${API_URL}/${CAR_MEDIA_FOLDER}`;
