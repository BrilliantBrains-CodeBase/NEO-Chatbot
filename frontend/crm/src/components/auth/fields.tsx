"use client";

import { useState, type InputHTMLAttributes } from "react";

/** A password input with the design's Show / Hide button. */
export function PasswordInput(props: InputHTMLAttributes<HTMLInputElement>) {
  const [shown, setShown] = useState(false);
  return (
    <span className="pw">
      <input {...props} type={shown ? "text" : "password"} />
      <button type="button" className="eye" onClick={() => setShown(!shown)}>
        {shown ? "Hide" : "Show"}
      </button>
    </span>
  );
}

/** The red message under a field; empty renders nothing (the design's .err:empty). */
export function FieldError({ message, id }: { message?: string; id?: string }) {
  return (
    <span className="err" id={id} role={message ? "alert" : undefined}>
      {message ?? ""}
    </span>
  );
}
