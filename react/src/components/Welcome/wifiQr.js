// Payload for the de-facto WiFi QR format that iOS and Android cameras both understand:
//   WIFI:T:<WPA|WEP|nopass>;S:<ssid>;P:<password>;;
// The characters \ ; , : " are special inside a field and must be backslash-escaped.
export function escapeWifiField(value) {
    return value.replace(/([\\;,:"])/g, '\\$1');
}

export function wifiQrPayload({ wifi_ssid, wifi_password, wifi_security }) {
    if (!wifi_ssid) return null;
    const open = wifi_security === 'nopass';
    const pass = open ? '' : `P:${escapeWifiField(wifi_password ?? '')};`;
    return `WIFI:T:${open ? 'nopass' : wifi_security};S:${escapeWifiField(wifi_ssid)};${pass};`;
}

// The address the second QR code points at: deliberately the bare site address, with no
// meeting id, so it is short enough to type by hand. "/" redirects to the meeting in
// progress. public_base_url (a Settings override) wins over the page's own origin, which
// is wrong when the TV loaded the page via localhost.
export function meetingUrl(publicBaseUrl, origin) {
    return publicBaseUrl || origin;
}
