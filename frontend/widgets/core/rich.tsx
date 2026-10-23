import { Fragment } from 'preact';

// Web addresses in bot text ("Map: https://maps.app.goo.gl/..."). Only http(s); a full stop or bracket
// right after the address is not part of it.
const URL_RE = /(https?:\/\/[^\s<>"]+[^\s<>".,;:!?)\]])/g;

// Renders bot text safely: "**bold**", line breaks and web addresses as links. Never uses innerHTML.
export function Rich({ text }: { text: string }) {
  return (
    <>
      {text.split('\n').map((line, i) => (
        <Fragment key={i}>
          {i > 0 && <br />}
          {line
            .split(/\*\*(.+?)\*\*/g)
            .map((part, j) => (j % 2 ? <b key={j}>{links(part)}</b> : links(part)))}
        </Fragment>
      ))}
    </>
  );
}

function links(text: string) {
  return text.split(URL_RE).map((part, k) =>
    k % 2 ? (
      <a key={k} class="nb-link" href={part} target="_blank" rel="noopener noreferrer">
        {part}
      </a>
    ) : (
      part
    ),
  );
}
