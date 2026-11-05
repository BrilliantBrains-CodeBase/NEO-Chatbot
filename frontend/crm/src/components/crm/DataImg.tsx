import type { ImgHTMLAttributes } from "react";

/** An uploaded image kept as a data: URL (logo, favicon, photo). next/image has nothing to optimise there. */
export default function DataImg(props: ImgHTMLAttributes<HTMLImageElement> & { src: string; alt: string }) {
  // eslint-disable-next-line @next/next/no-img-element, jsx-a11y/alt-text
  return <img {...props} />;
}
