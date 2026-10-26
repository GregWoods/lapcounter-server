import { CAR_MEDIA_URL } from '../../endpoints.js';

const defaultCarImg = `${CAR_MEDIA_URL}/GT_AA_Generic.jpg`;
export const carImageUrl = (picture) => picture ? `${CAR_MEDIA_URL}/${picture}` : defaultCarImg;
export const onCarImgError = (e) => { e.target.onerror = null; e.target.src = defaultCarImg; };
