"use client";

import type { ReactNode } from "react";

/** A screen's header from the design, with a note that its content comes in a later step. */
export default function Placeholder({
  title,
  description,
  next,
}: {
  title: ReactNode;
  description: ReactNode;
  next: string[];
}) {
  return (
    <>
      <div className="ph">
        <div>
          <h1>{title}</h1>
          <p>{description}</p>
        </div>
      </div>
      <div className="empty">
        <h2>Built in a later step</h2>
        This screen follows the approved design. Coming here:
        <br />
        <ul>
          {next.map((x) => (
            <li key={x}>{x}</li>
          ))}
        </ul>
      </div>
    </>
  );
}
