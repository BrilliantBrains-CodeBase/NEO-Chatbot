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
import { api, ApiError, CODE_NEEDED, REFRESH_MS, type Inbox, type Me } from "@/lib/api";
import {
  desktopAlert,
  playTone,
  type ClinicCounts,
  type NotePrefs,
  type NoteSummary,
} from "@/lib/notifications";
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
  /** The selected clinic's id; undefined while loading. */
  clinicId: string | undefined;
  /** The bell's counts for this person in this clinic; null while loading. */
  notes: NoteSummary | null;
  /** The new counts, after an action on a notification. */
  setNotes: (s: NoteSummary) => void;
  /** The bell's counts in every clinic this person has, by clinic id (several clinics only). */
  clinicNotes: ClinicCounts;
  /** This person's bell settings, the same on every computer. */
  prefs: NotePrefs;
  savePrefs: (p: NotePrefs) => Promise<void>;
  /** "hidden": no bell for this person here. "error": the last read failed, so the counts may be old or missing. */
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
  const [inbox, setInbox] = useState<{ clinic: string; counts: Record<string, number> } | null>(null);
  const [noted, setNoted] = useState<{ clinic: string; s: NoteSummary } | null>(null);
  const [clinicNotes, setClinicNotes] = useState<ClinicCounts>({});
  const [prefs, setPrefs] = useState<NotePrefs>({ off_kinds: [], sound: false, desktop: false });
  // What the last read found, to notice something new; and the settings, read when something arrives.
  const lastNotes = useRef<{ clinic: string; s: NoteSummary } | null>(null);
  const alerts = useRef(prefs);
  useEffect(() => {
    alerts.current = prefs;
  }, [prefs]);
  const [inboxVersion, setInboxVersion] = useState(0);
  const refreshInbox = useCallback(() => setInboxVersion((v) => v + 1), []);
  const [inboxFailed, setInboxFailed] = useState<string | null>(null); // the clinic whose last read failed
  const canInbox = !!me && level(me, clinic, "inbox") !== "hidden";
  // The bell shows to anyone who can see one of the screens its notifications belong to.
  const canBell =
    !!me && ["inbox", "leads", "team", "dash_integrations"].some((s) => level(me, clinic, s) !== "hidden");
  const toastRef = useRef<(m: string) => void>(() => {});
  const several = clinics.length > 1;
  useEffect(() => {
    if (!me) return;
    let live = true;
    api<NotePrefs>("/v1/crm/notifications/prefs").then(
      (p) => live && setPrefs(p),
      () => {},
    );
    return () => {
      live = false;
    };
  }, [me]);
  // On every page: read now, every REFRESH_MS, and on coming back to the tab. The Inbox's counts wait while the
  // tab is hidden; the bell's do not, or a desktop alert could never fire while someone works in another tab.
  useEffect(() => {
    if (!clinicId || !canBell) return;
    let live = true;
    let lastRead = 0;
    const readNotes = () => {
      if (several)
        api<ClinicCounts>("/v1/crm/notifications/clinics").then(
          (d) => live && setClinicNotes(d),
          () => {},
        );
      return api<NoteSummary>(`/v1/crm/notifications/summary?clinic=${clinicId}`).then((s) => {
        if (!live) return;
        const was = lastNotes.current;
        if (was && was.clinic === clinicId) {
          const urgent = s.urgent > was.s.urgent;
          if (urgent || s.unread > was.s.unread) {
            toastRef.current(urgent ? "Emergency: check the bell" : "New notification");
            if (alerts.current.sound) playTone(urgent);
            if (alerts.current.desktop && (urgent || document.hidden)) desktopAlert(urgent);
          }
        }
        lastNotes.current = { clinic: clinicId, s };
        setNoted({ clinic: clinicId, s });
      });
    };
    const readInbox = () =>
      // One row is enough: the counts come with any page of the list.
      api<Inbox>(`/v1/crm/inbox?clinic=${clinicId}&limit=1`).then((d) => {
        if (live) setInbox({ clinic: clinicId, counts: Object.fromEntries(d.pending.map((c) => [c.key, c.count])) });
      });
    const read = () => {
      lastRead = Date.now();
      Promise.all([readNotes(), document.hidden || !canInbox ? null : readInbox()]).then(
        () => {
          if (live) setInboxFailed(null);
        },
        () => {
          if (live) setInboxFailed(clinicId);
        },
      );
    };
    read();
    const timer = setInterval(read, REFRESH_MS);
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
  }, [clinicId, canBell, canInbox, several, inboxVersion]);

  const setNotes = useCallback(
    (s: NoteSummary) => {
      if (!clinicId) return;
      lastNotes.current = { clinic: clinicId, s };
      setNoted({ clinic: clinicId, s });
    },
    [clinicId],
  );
  const savePrefs = useCallback(
    async (p: NotePrefs) => {
      setPrefs(p);
      await api("/v1/crm/notifications/prefs", { method: "PUT", body: JSON.stringify(p) });
      lastNotes.current = null; // a type turned back on is not something new arriving
      refreshInbox(); // types turned off change the counts
    },
    [refreshInbox],
  );

  const [toastText, setToastText] = useState("");
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const toast = useCallback((m: string) => {
    setToastText(m);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setToastText(""), 1800);
  }, []);
  useEffect(() => {
    toastRef.current = toast;
  }, [toast]);

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
      clinicId,
      notes: noted && noted.clinic === clinicId ? noted.s : null,
      setNotes,
      clinicNotes,
      prefs,
      savePrefs,
      inboxStatus: me && !canBell
        ? "hidden"
        : clinicId && inboxFailed === clinicId
          ? "error"
          : noted && noted.clinic === clinicId
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
  }, [ready, me, clinics, clinic, clinicId, signOut, inbox, noted, setNotes, clinicNotes, prefs, savePrefs, inboxFailed, canBell, refreshInbox, toast, toastText, drawer, modal]);

  return <CrmContext.Provider value={value}>{children}</CrmContext.Provider>;
}
