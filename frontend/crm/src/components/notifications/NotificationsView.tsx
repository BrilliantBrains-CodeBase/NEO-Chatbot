"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useCrm } from "@/components/crm/CrmProvider";
import Loading from "@/components/crm/Loading";
import NotificationRows, { useNotes } from "@/components/crm/NotificationRows";
import Pager from "@/components/crm/Pager";
import { NOTE_KINDS } from "@/lib/notifications";

const PAGE_SIZE = 30;

/** Every notification of this clinic for this person: filters, pages, and the same actions as the bell. */
export default function NotificationsView() {
  const crm = useCrm();
  const router = useRouter();
  const [show, setShow] = useState<"all" | "unread">("all");
  const [kind, setKind] = useState("");
  const [page, setPage] = useState(1);
  const allowed = crm.inboxStatus !== "hidden";
  const { data, error, act, retry } = useNotes(
    { show, kind: kind || undefined, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE },
    allowed,
  );
  const unread = crm.notes?.unread ?? 0;

  if (!allowed) {
    return (
      <div className="ph">
        <div>
          <h1>Notifications</h1>
          <p>Your role does not include notifications in this clinic.</p>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="ph">
        <div>
          <h1>Notifications</h1>
          <p>{unread ? `${unread} unread in ${crm.clinic}` : `Nothing unread in ${crm.clinic}`}</p>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <button className="btn g sm" disabled={!unread} onClick={() => void act("read-all", true)}>
            Mark all read
          </button>
          <button className="btn g sm" onClick={() => void act("clear-read", true)}>
            Clear read
          </button>
        </div>
      </div>

      <div className="row" style={{ gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
        <div className="nt-tabs" role="tablist" aria-label="Show">
          {(["all", "unread"] as const).map((s) => (
            <button
              key={s}
              role="tab"
              aria-selected={show === s}
              className={show === s ? "on" : ""}
              onClick={() => {
                setShow(s);
                setPage(1);
              }}
            >
              {s === "all" ? "All" : "Unread"}
            </button>
          ))}
        </div>
        <select
          className="sel"
          aria-label="Type"
          value={kind}
          onChange={(e) => {
            setKind(e.target.value);
            setPage(1);
          }}
        >
          <option value="">All types</option>
          <option value="emergency">Emergencies</option>
          {NOTE_KINDS.map((k) => (
            <option key={k.id} value={k.id}>
              {k.label}
            </option>
          ))}
        </select>
      </div>

      <div className="card nt-page">
        {error && !data ? (
          <div className="nt-empty">
            <p>{error}</p>
            <button className="nt-retry" onClick={retry}>
              Try again
            </button>
          </div>
        ) : !data ? (
          <Loading inline label="Loading notifications" />
        ) : data.items.length === 0 ? (
          <div className="nt-empty">
            <p>{show === "unread" || kind ? "Nothing matches." : "You're all caught up."}</p>
          </div>
        ) : (
          <NotificationRows items={data.items} act={act} onOpen={(href) => router.push(href)} />
        )}
      </div>
      {data && data.total > 0 && (
        <Pager page={page} size={PAGE_SIZE} shown={data.items.length} total={data.total} onPage={setPage} />
      )}
    </>
  );
}
