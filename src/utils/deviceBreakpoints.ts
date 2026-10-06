/** Viewport width below this is treated as mobile (phones). Tablets use desktop shell for now. */
export const MOBILE_MAX_WIDTH_PX = 767;

export const MOBILE_MEDIA_QUERY = `(max-width: ${MOBILE_MAX_WIDTH_PX}px)`;
export const TOUCH_PRIMARY_MEDIA_QUERY = '(pointer: coarse)';
export const STANDALONE_MEDIA_QUERY = '(display-mode: standalone)';
