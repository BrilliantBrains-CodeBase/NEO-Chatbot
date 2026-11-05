// Uploaded images are made small in the browser before they are saved: the CRM keeps them in the database
// (Clinic settings: logo and favicon; My profile: photo), so a 4 MB photo becomes a few KB.

const MAX_FILE = 5 * 1024 * 1024;
const TYPES = ["image/png", "image/jpeg", "image/webp", "image/svg+xml", "image/x-icon", "image/vnd.microsoft.icon", "image/gif"];

export type Fit = {
  /** The largest width and height, in pixels. Smaller images are not made larger. */
  width: number;
  height: number;
  /** Cut to a square from the middle (photos, favicons) instead of fitting the whole image. */
  square?: boolean;
  /** "image/png" keeps transparency (logos); "image/jpeg" is smallest for photos. */
  type?: "image/png" | "image/jpeg" | "image/webp";
};

export class ImageError extends Error {}

function load(file: File): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve(img);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new ImageError("That file could not be opened as an image."));
    };
    img.src = url;
  });
}

/** The file as a small data:image, ready to save. */
export async function fitImage(file: File, fit: Fit): Promise<string> {
  if (!TYPES.includes(file.type)) throw new ImageError("Choose a PNG, JPG, WebP, SVG or ICO image.");
  if (file.size > MAX_FILE) throw new ImageError("The image must be under 5 MB.");
  const img = await load(file);
  // An SVG without a set size reports 0 or a small default: draw it at the largest size allowed.
  const w0 = img.naturalWidth || fit.width;
  const h0 = img.naturalHeight || fit.height;
  let sx = 0;
  let sy = 0;
  let sw = w0;
  let sh = h0;
  if (fit.square) {
    const side = Math.min(w0, h0);
    sx = (w0 - side) / 2;
    sy = (h0 - side) / 2;
    sw = sh = side;
  }
  const scale = Math.min(1, fit.width / sw, fit.height / sh);
  const vector = file.type === "image/svg+xml";
  const width = Math.max(1, Math.round(vector ? Math.min(fit.width, fit.height * (sw / sh)) : sw * scale));
  const height = Math.max(1, Math.round(vector ? width * (sh / sw) : sh * scale));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new ImageError("This browser cannot prepare the image.");
  const type = fit.type ?? "image/png";
  if (type === "image/jpeg") {
    ctx.fillStyle = "#fff"; // JPG has no transparency
    ctx.fillRect(0, 0, width, height);
  }
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(img, sx, sy, sw, sh, 0, 0, width, height);
  return canvas.toDataURL(type, 0.86);
}
