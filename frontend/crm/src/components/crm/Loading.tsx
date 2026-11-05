/** The CRM's one loading sign: a turning ring in the middle of the screen. `inline` keeps it where it is
 * written, for a part of a panel or a pop-up form. The ring appears after a moment (crm.css), so a quick
 * load does not flash it. */
export default function Loading({ inline = false, label = "Loading" }: { inline?: boolean; label?: string }) {
  return (
    <div className={inline ? "loading inline" : "loading"} role="status" aria-label={label}>
      <span className="spinner" aria-hidden="true" />
    </div>
  );
}
