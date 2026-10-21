import { Fragment } from 'preact';

// Renders bot text safely: "**bold**" and line breaks only. Never uses innerHTML.
export function Rich({ text }: { text: string }) {
  return (
    <>
      {text.split('\n').map((line, i) => (
        <Fragment key={i}>
          {i > 0 && <br />}
          {line.split(/\*\*(.+?)\*\*/g).map((part, j) => (j % 2 ? <b key={j}>{part}</b> : part))}
        </Fragment>
      ))}
    </>
  );
}
