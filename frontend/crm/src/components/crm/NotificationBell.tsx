"use client";

import { useEffect, useState, type MouseEvent, type RefObject } from "react";
import Loading from "./Loading";
import { useCrm } from "./CrmProvider";
import Icon from "./Icon";
import NotificationRows, { useNotes } from "./NotificationRows";

const SHOWN = 20;

/** The top bar's bell: unread count, and a panel to read, clear and open notifications. */
export default function NotificationBell({
  open,
  boxRef,
  onToggle,
  onGo,
}: {
  open: boolean;
  boxRef: RefObject<HTMLDivElement | null>;
  onToggle: (e: MouseEvent) => void;
  onGo: (href: string) => void;
}) {
  const crm = useCrm();
  const [show, setShow] = useState<"all" | "unread">("all");
  const { data, error, act, retry } = useNotes({ show, limit: SHOWN, offset: 0 }, open);
  const unread = crm.notes?.unread ?? 0;
  const urgent = crm.notes?.urgent ?? 0;
  const failed = crm.inboxStatus === "error" && !crm.notes;

  // The count in the browser tab too, so it shows from another tab.
  useEffect(() => {
    const plain = document.title.replace(/^\(\d+\+?\)\s*/, "");
    document.title = unread ? `(${unread > 99 ? "99+" : unread}) ${plain}` : plain;
  });

  return (
    <div ref={boxRef} className="tb-menu">
      <button
        className={`ib tb-bell${urgent ? " urgent" : ""}`}
        aria-label={
          urgent
            ? `Notifications, ${urgent} emergency waiting, ${unread} unread`
            : unread
              ? `Notifications, ${unread} unread`
              : "Notifications"
        }
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={onToggle}
      >
        <Icon name="bell" />
        {/* Remounting on a new count replays the badge's pop. An emergency already read still shows. */}
        {unread > 0 ? (
          <b key={unread}>{unread > 99 ? "99+" : unread}</b>
        ) : urgent > 0 ? (
          <b>!</b>
        ) : null}
      </button>

      <div className={`pmenu tb-notes${open ? " on" : ""}`} role="dialog" aria-label="Notifications">
        <div className="nt-top">
          <b>Notifications</b>
          <span className="nt-top-acts">
            <button disabled={!unread} onClick={() => void act("read-all", true)}>
              Mark all read
            </button>
            <button onClick={() => void act("clear-read", true)}>Clear read</button>
          </span>
        </div>
        <div className="nt-tabs" role="tablist" aria-label="Show">
          {(["all", "unread"] as const).map((s) => (
            <button
              key={s}
              role="tab"
              aria-selected={show === s}
              className={show === s ? "on" : ""}
              onClick={() => setShow(s)}
            >
              {s === "all" ? "All" : `Unread${unread ? ` (${unread > 99 ? "99+" : unread})` : ""}`}
            </button>
          ))}
        </div>

        <div className="tb-notes-list">
          {failed || (error && !data) ? (
            <div className="nt-empty">
              <p>Could not load notifications.</p>
              <button
                className="nt-retry"
                onClick={() => {
                  retry();
                  crm.refreshInbox();
                }}
              >
                Try again
              </button>
            </div>
          ) : !data ? (
            <Loading inline label="Loading notifications" />
          ) : data.items.length === 0 ? (
            <div className="nt-empty">
              <p>{show === "unread" ? "No unread notifications." : "You're all caught up."}</p>
            </div>
          ) : (
            <NotificationRows items={data.items} act={act} onOpen={onGo} />
          )}
        </div>

        <div className="nt-foot">
          <button className="tb-all" onClick={() => onGo("/notifications")}>
            Show all
          </button>
          <button
            className="nt-ic"
            title="Notification settings"
            aria-label="Notification settings"
            onClick={() => onGo("/settings")}
          >
            <Icon name="set" />
          </button>
        </div>
      </div>
    </div>
  );
}
