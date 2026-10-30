"use client";

import { useCrm } from "@/components/crm/CrmProvider";

// The main template (Neo Follicle): its canvas, Templates and Appearance are what other clinics show until they
// change that part. On Neo Follicle: "Publish for all clinics" (BB Admin only). Elsewhere: whether this part
// follows Neo Follicle or is the clinic's own, and the switch between them.

export const MAIN = "CL01";
export type Part = "flow" | "template" | "appearance";
const NAMES: Record<Part, string> = {
  flow: "canvas",
  template: "template",
  appearance: "appearance",
};

/** The Publish button's words: on Neo Follicle it changes Neo Follicle only. */
export const publishLabel = (clinicId?: string) =>
  clinicId === MAIN ? "Publish for Neo Follicle only" : "Publish";

export default function MainTemplateBar({
  clinicId,
  part,
  follows,
  mainBehind,
  changed,
  busy,
  blocked,
  call,
}: {
  clinicId?: string;
  part: Part;
  follows?: string[];
  mainBehind?: boolean;
  changed: boolean;
  busy: boolean;
  blocked?: boolean; // unsaved changes or problems: no switching or publishing
  call: (
    path: string,
    method: string,
    body: object | undefined,
    done: string,
  ) => Promise<unknown>;
}) {
  const { me } = useCrm();
  if (!clinicId) return null;
  const name = NAMES[part];

  if (clinicId === MAIN) {
    if (!me?.bb_admin) return null; // managers see Neo Follicle's own Publish only
    return (
      <div
        className="card row"
        style={{
          gap: 10,
          alignItems: "center",
          padding: "10px 14px",
          marginBottom: 14,
        }}
      >
        <span className="badge b-vi">Main template</span>
        <span className="sub2" style={{ flex: 1 }}>
          Clinics that follow Neo Follicle show its {name}, with their own
          clinic and bot name.{" "}
          {mainBehind && !changed
            ? "Neo Follicle's live version is not yet for all clinics."
            : ""}
        </span>
        <button
          className="btn"
          disabled={busy || blocked || !(changed || mainBehind)}
          onClick={() => {
            if (
              window.confirm(
                "Publish Neo Follicle's canvas, Templates and Appearance for every clinic that follows it?",
              )
            )
              void call(
                "publish?for_all=true",
                "POST",
                undefined,
                "Published for all clinics",
              );
          }}
        >
          Publish for all clinics
        </button>
      </div>
    );
  }

  const following = (follows ?? []).includes(part);
  return (
    <div
      className="card row"
      style={{
        gap: 10,
        alignItems: "center",
        padding: "10px 14px",
        marginBottom: 14,
      }}
    >
      <span className={`badge ${following ? "b-vi" : "b-bk"}`}>
        {following
          ? "Following Neo Follicle (main template)"
          : "This clinic's own"}
      </span>
      <span className="sub2" style={{ flex: 1 }}>
        {following
          ? `This ${name} comes from Neo Follicle, with your clinic and bot name. Saving a change makes it your own.`
          : `Changes to Neo Follicle's ${name} do not reach this clinic.`}
      </span>
      <button
        className="btn g"
        disabled={busy || blocked}
        onClick={() => {
          if (following)
            void call(
              "main-template",
              "PUT",
              { part, follow: false },
              `This ${name} is now your own`,
            );
          else if (
            window.confirm(
              `Follow Neo Follicle's ${name} again? This clinic's own ${name} is set aside.`,
            )
          )
            void call(
              "main-template",
              "PUT",
              { part, follow: true },
              `Following Neo Follicle's ${name} again`,
            );
        }}
      >
        {following ? "Make it our own" : "Follow main again"}
      </button>
    </div>
  );
}
