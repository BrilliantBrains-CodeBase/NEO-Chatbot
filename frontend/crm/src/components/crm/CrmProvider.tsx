"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, CODE_NEEDED, type Inbox, type InboxItem, type Me } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import {
  CLINICS,
  sampleLeads,
  sampleRequests,
  type Clinic,
  type Lead,
  type Req,
  type ReqKind,
  type Stage,
} from "@/lib/sample-data";

type Modal = { title: string; body: ReactNode };

type Crm = {
  /** False until the data has loaded (counts are hidden until then). */
  ready: boolean;
  /** The signed-in person (from GET /v1/crm/me); null while loading. */
  me: Me | null;
  /** The clinics this person may see. */
  clinics: Clinic[];
  clinic: Clinic;
  setClinic: (c: Clinic) => void;
  signOut: () => Promise<void>;
  leads: Lead[];
  requests: Req[];
  /** Leads in a stage ("lo" also counts Invalid, like the design's "Lost & Invalid"). */
  stageCount: (s: Stage) => number;
  /** Pending requests of a kind. */
  pending: (k: ReqKind) => number;
  /** Booking, online, cancel and reschedule requests waiting (the Inbox count). */
  inboxCount: number;
  /** Live pending requests per type (book, online, cancel, reschedule, callback, question); null while loading. */
  inbox: Record<string, number> | null;
  /** The pending requests themselves (oldest first), for the notifications list. */
  inboxItems: InboxItem[];
  /** Load the pending counts again (after a request is handled). */
  refreshInbox: () => void;
  toast: (message: string) => void;
  toastText: string;
  drawer: ReactNode | null;
  openDrawer: (content: ReactNode) => void;
  closeDrawer: () => void;
  modal: Modal | null;
  openModal: (m: Modal) => void;
  closeModal: () => void;
};

const CrmContext = createContext<Crm | null>(null);

// The time the CRM opened in the browser; null while the server pre-renders the frame.
let openedAt: Date | null = null;
const noSubscription = () => () => {};
function useBrowserNow(): Date | null {
  return useSyncExternalStore(
    noSubscription,
    () => (openedAt ??= new Date()),
    () => null,
  );
}

export function useCrm(): Crm {
  const c = useContext(CrmContext);
  if (!c) throw new Error("useCrm must be used inside CrmProvider");
  return c;
}

export default function CrmProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  // Who is signed in. Without CRM access (expired sign-in, removed or not approved): back to sign-in.
  const [me, setMe] = useState<Me | null>(null);
  useEffect(() => {
    let live = true;
    api<Me>("/v1/crm/me")
      .then((m) => live && setMe(m))
      .catch(async (e: unknown) => {
        if (e instanceof ApiError && e.message === CODE_NEEDED) {
          router.replace("/verify"); // 2-step login: this sign-in still needs its emailed code
          return;
        }
        if (e instanceof ApiError && (e.status === 401 || e.status === 403)) {
          await supabase().auth.signOut();
          router.replace("/sign-in");
        }
      });
    return () => {
      live = false;
    };
  }, [router]);
  const signOut = useCallback(async () => {
    await supabase().auth.signOut();
    router.replace("/sign-in");
  }, [router]);
  // Every clinic this person may see, as the backend lists them (any clinic added in Login & security).
  const clinics = useMemo(() => (me?.clinics ?? []).map((c) => c.name as Clinic), [me]);
  const [chosen, setClinic] = useState<Clinic | null>(null);
  const clinic = chosen && clinics.includes(chosen) ? chosen : (clinics[0] ?? CLINICS[0]);
  // Sample data per clinic (replaced by backend data screen by screen). Made in the browser only, after the
  // frame shows: it depends on the current time, which the server must not use while pre-rendering.
  const now = useBrowserNow();
  const { leads, requests } = useMemo(() => {
    if (!now) return { leads: [], requests: [] };
    // The leftover sample data knows only its own clinic names; any other clinic uses one of them.
    const sample = CLINICS.includes(clinic) ? clinic : CLINICS[2];
    const l = sampleLeads(sample, now);
    return { leads: l, requests: sampleRequests(sample, l, now) };
  }, [clinic, now]);
  const ready = now !== null;

  const clinicId = me?.clinics.find((c) => c.name === clinic)?.id;
  const [inbox, setInbox] = useState<{ clinic: string; counts: Record<string, number>; items: InboxItem[] } | null>(
    null,
  );
  const [inboxVersion, setInboxVersion] = useState(0);
  const refreshInbox = useCallback(() => setInboxVersion((v) => v + 1), []);
  useEffect(() => {
    if (!clinicId) return;
    let live = true;
    api<Inbox>(`/v1/crm/inbox?clinic=${clinicId}`).then(
      (d) =>
        live &&
        setInbox({ clinic: clinicId, counts: Object.fromEntries(d.pending.map((c) => [c.key, c.count])), items: d.items }),
      () => {},
    );
    return () => {
      live = false;
    };
  }, [clinicId, inboxVersion]);

  const [toastText, setToastText] = useState("");
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const toast = useCallback((m: string) => {
    setToastText(m);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setToastText(""), 1800);
  }, []);

  const [drawer, setDrawer] = useState<ReactNode | null>(null);
  const [modal, setModal] = useState<Modal | null>(null);

  const value = useMemo<Crm>(() => {
    const stageCount = (s: Stage) =>
      leads.filter((l) => l.st === s || (s === "lo" && l.st === "in")).length;
    const pending = (k: ReqKind) => requests.filter((r) => r.kind === k && r.status === "pending").length;
    return {
      ready,
      me,
      clinics,
      clinic,
      setClinic,
      signOut,
      leads,
      requests,
      stageCount,
      pending,
      inboxCount: (["appt", "online", "cancel", "resch"] as ReqKind[]).reduce((a, k) => a + pending(k), 0),
      inbox: inbox && inbox.clinic === clinicId ? inbox.counts : null,
      inboxItems: inbox && inbox.clinic === clinicId ? inbox.items : [],
      refreshInbox,
      toast,
      toastText,
      drawer,
      openDrawer: setDrawer,
      closeDrawer: () => setDrawer(null),
      modal,
      openModal: setModal,
      closeModal: () => setModal(null),
    };
  }, [ready, me, clinics, clinic, clinicId, signOut, leads, requests, inbox, refreshInbox, toast, toastText, drawer, modal]);

  return <CrmContext.Provider value={value}>{children}</CrmContext.Provider>;
}
