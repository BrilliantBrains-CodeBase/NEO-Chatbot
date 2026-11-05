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
import { level } from "@/lib/access";
import { api, ApiError, CODE_NEEDED, REFRESH_MS, type Inbox, type InboxItem, type Me } from "@/lib/api";
import { supabase } from "@/lib/supabase";

export type Clinic = string; // a clinic's name, as the backend lists them
type Modal = { title: string; body: ReactNode };

type Crm = {
  /** False until the data has loaded (counts are hidden until then). */
  ready: boolean;
  /** The signed-in person (from GET /v1/crm/me); null while loading. */
  me: Me | null;
  /** Replace the signed-in person (after My profile saves a change). */
  setMe: (m: Me) => void;
  /** The clinics this person may see. */
  clinics: Clinic[];
  clinic: Clinic;
  setClinic: (c: Clinic) => void;
  signOut: () => Promise<void>;
  /** Live pending requests per type (book, online, cancel, reschedule, callback, question); null while loading. */
  inbox: Record<string, number> | null;
  /** The pending requests themselves (newest first), for the notifications list. */
  inboxItems: InboxItem[];
  /** "hidden": this person has no Inbox here. "error": the last read failed, so the counts may be old or missing. */
  inboxStatus: "hidden" | "loading" | "ready" | "error";
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
  const clinic = chosen && clinics.includes(chosen) ? chosen : (clinics[0] ?? "");
  const ready = useBrowserNow() !== null;

  const clinicId = me?.clinics.find((c) => c.name === clinic)?.id;
  const [inbox, setInbox] = useState<{ clinic: string; counts: Record<string, number>; items: InboxItem[] } | null>(
    null,
  );
  const [inboxVersion, setInboxVersion] = useState(0);
  const refreshInbox = useCallback(() => setInboxVersion((v) => v + 1), []);
  const [inboxFailed, setInboxFailed] = useState<string | null>(null); // the clinic whose last read failed
  const canInbox = !!me && level(me, clinic, "inbox") !== "hidden";
  // On every page: read now, every REFRESH_MS while the tab is in view, and on coming back to the tab.
  useEffect(() => {
    if (!clinicId || !canInbox) return;
    let live = true;
    let lastRead = 0;
    const read = () => {
      lastRead = Date.now();
      api<Inbox>(`/v1/crm/inbox?clinic=${clinicId}`).then(
        (d) => {
          if (!live) return;
          setInbox({ clinic: clinicId, counts: Object.fromEntries(d.pending.map((c) => [c.key, c.count])), items: d.items });
          setInboxFailed(null);
        },
        () => {
          if (live) setInboxFailed(clinicId);
        },
      );
    };
    read();
    const timer = setInterval(() => {
      if (!document.hidden) read();
    }, REFRESH_MS);
    // Coming back fires both events: one read is enough.
    const onReturn = () => {
      if (!document.hidden && Date.now() - lastRead > 5000) read();
    };
    document.addEventListener("visibilitychange", onReturn);
    window.addEventListener("focus", onReturn);
    return () => {
      live = false;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onReturn);
      window.removeEventListener("focus", onReturn);
    };
  }, [clinicId, canInbox, inboxVersion]);

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
    return {
      ready,
      me,
      setMe,
      clinics,
      clinic,
      setClinic,
      signOut,
      inbox: inbox && inbox.clinic === clinicId ? inbox.counts : null,
      inboxItems: inbox && inbox.clinic === clinicId ? inbox.items : [],
      inboxStatus: me && !canInbox
        ? "hidden"
        : clinicId && inboxFailed === clinicId
          ? "error"
          : inbox && inbox.clinic === clinicId
            ? "ready"
            : "loading",
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
  }, [ready, me, clinics, clinic, clinicId, signOut, inbox, inboxFailed, canInbox, refreshInbox, toast, toastText, drawer, modal]);

  return <CrmContext.Provider value={value}>{children}</CrmContext.Provider>;
}
