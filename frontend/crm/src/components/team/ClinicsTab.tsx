"use client";

import { useEffect, useState } from "react";
import Loading from "@/components/crm/Loading";
import { useCrm } from "@/components/crm/CrmProvider";
import { api, type Me } from "@/lib/api";
import { MAIN } from "@/components/assistant/MainTemplateBar";
import { Confirm, message, RowMenu, type MenuItem } from "./shared";

// Team → Clinics (Super Admin): every clinic in the project, Add clinic (the next free code, a copy of another
// clinic's setup and chat, an optional first admin invite), Deactivate / Activate and Delete.

type Clinic = {
  id: string;
  name: string;
  bot_name: string;
  active: boolean;
  is_test: boolean;
  members: number;
};

export default function ClinicsTab({ onOpen }: { onOpen: () => void }) {
  const { toast, openModal, closeModal, clinics, setClinic, setMe } = useCrm();
  const [list, setList] = useState<Clinic[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    api<Clinic[]>("/v1/crm/clinics").then(
      (x) => live && setList(x),
      (e) => live && setError(message(e, "Could not load the clinics.")),
    );
    return () => {
      live = false;
    };
  }, []);

  /** A change to the clinics; the clinic switcher in the top bar follows it. */
  async function call(path: string, method: string, body?: object) {
    setList(
      await api<Clinic[]>(`/v1/crm/clinics${path}`, {
        method,
        body: body ? JSON.stringify(body) : undefined,
      }),
    );
    setMe(await api<Me>("/v1/crm/me"));
  }

  if (error && !list) return <div className="warnbox">{error}</div>;
  if (!list) return <Loading />;

  const menu = (c: Clinic): MenuItem[] => [
    {
      label: "Open its team",
      disabled: !clinics.includes(c.name),
      onClick: () => {
        setClinic(c.name);
        onOpen();
      },
    },
    ...(c.is_test
      ? []
      : [
          {
            label: c.active ? "Deactivate" : "Activate",
            onClick: () =>
              openModal({
                title: c.active ? `Deactivate ${c.name}` : `Activate ${c.name}`,
                body: (
                  <Confirm
                    text={
                      c.active
                        ? `Its chat and CRM stop. Nothing is deleted, and you can activate it again.`
                        : `Its chat and CRM start again.`
                    }
                    action={c.active ? "Deactivate" : "Activate"}
                    danger={c.active}
                    onConfirm={async () => {
                      await call(`/${c.id}`, "PUT", { active: !c.active });
                      toast(c.active ? "Deactivated" : "Activated");
                    }}
                    onClose={closeModal}
                  />
                ),
              }),
          },
        ]),
    ...(!c.is_test && c.id !== MAIN
      ? [
          {
            label: "Delete",
            danger: true,
            onClick: () =>
              openModal({
                title: `Delete ${c.name}`,
                body: (
                  <Confirm
                    text="Delete this clinic for good? Only a clinic with no leads, chats, doctors or integrations can be deleted."
                    action="Delete clinic"
                    danger
                    typed={c.id}
                    onConfirm={async () => {
                      await call(`/${c.id}`, "DELETE");
                      toast(`${c.name} deleted`);
                    }}
                    onClose={closeModal}
                  />
                ),
              }),
          },
        ]
      : []),
  ];

  return (
    <>
      <div className="tm-head">
        <div>
          <h2>Clinics</h2>
          <p>
            Every clinic in this project. Only Super Admins add or change
            clinics.
          </p>
        </div>
        <button
          type="button"
          className="btn"
          onClick={() =>
            openModal({
              title: "Add a clinic",
              body: (
                <AddClinicForm
                  clinics={list}
                  add={async (body, name) => {
                    await call("", "POST", body);
                    toast(`${name} added`);
                    closeModal();
                  }}
                  onClose={closeModal}
                />
              ),
            })
          }
        >
          Add clinic
        </button>
      </div>
      {error && (
        <div className="warnbox" role="alert" style={{ marginBottom: 12 }}>
          {error}
        </div>
      )}
      <div className="tw">
        <table className="tm-table">
          <thead>
            <tr>
              <th>Clinic</th>
              <th>Code</th>
              <th>Chatbot name</th>
              <th>Members</th>
              <th>Status</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {list.map((c) => (
              <tr key={c.id}>
                <td className="nm">
                  {c.name}
                  {c.is_test && (
                    <span className="badge b-bk" style={{ marginLeft: 6 }}>
                      Test
                    </span>
                  )}
                </td>
                <td className="tm-sub">{c.id}</td>
                <td>{c.bot_name}</td>
                <td>{c.members}</td>
                <td>
                  <span className={`tm-status${c.active ? " on" : ""}`}>
                    {c.active ? "Active" : "Inactive"}
                  </span>
                </td>
                <td className="tm-end">
                  <RowMenu label={`Actions for ${c.name}`} items={menu(c)} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

/** The first letter of each word, in capitals (Neo Fertility: NF); one word gives its first two letters. */
function initials(name: string): string {
  const words = name.match(/[A-Za-z0-9]+/g) ?? [];
  let code = words
    .map((w) => w[0])
    .join("")
    .toUpperCase();
  if (code.length < 2 && words[0]) code = words[0].slice(0, 2).toUpperCase();
  return code.replace(/^[^A-Z]+/, "").slice(0, 10);
}

const EMPTY = {
  name: "",
  code: "",
  bot_name: "",
  phone: "",
  whatsapp: "",
  website: "",
  manager_name: "",
  manager_email: "",
};

function AddClinicForm({
  clinics,
  add,
  onClose,
}: {
  clinics: Clinic[];
  add: (body: object, name: string) => Promise<void>;
  onClose: () => void;
}) {
  const [form, setForm] = useState({
    ...EMPTY,
    copy_from: clinics[0]?.id ?? MAIN,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // The short name follows the clinic name (its first letters) until staff type their own.
  const [ownCode, setOwnCode] = useState(false);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => {
    const value = e.target.value;
    if (k === "code") {
      setOwnCode(true);
      setForm({ ...form, code: value.toUpperCase().replace(/[^A-Z0-9]/g, "") });
    } else if (k === "name" && !ownCode) {
      setForm({ ...form, name: value, code: initials(value) });
    } else {
      setForm({ ...form, [k]: value });
    }
  };
  const codeOk = /^[A-Z][A-Z0-9]{1,9}$/.test(form.code);
  const ready =
    form.name.trim().length >= 2 && form.bot_name.trim().length >= 2 && codeOk;
  const field = (
    k: keyof typeof form,
    label: string,
    hint?: string,
    full?: boolean,
  ) => (
    <label className={`tm-field${full ? " full" : ""}`}>
      {label}
      <input
        className="f"
        placeholder={hint}
        value={form[k]}
        onChange={set(k)}
      />
    </label>
  );

  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError("");
        try {
          await add(
            Object.fromEntries(
              Object.entries(form).map(([k, v]) => [k, v.trim() || null]),
            ),
            form.name.trim(),
          );
        } catch (err) {
          setError(message(err, "Could not add the clinic. Please try again."));
          setBusy(false);
        }
      }}
    >
      <div className="tm-form">
        {field("name", "Clinic name", "e.g. Neo Fertility")}
        <label className="tm-field">
          Short name
          <input
            className="f"
            placeholder="e.g. NF"
            maxLength={10}
            value={form.code}
            onChange={set("code")}
            aria-invalid={form.code !== "" && !codeOk}
          />
          <span className="tm-hint">
            The clinic&apos;s code (NF, DS, NFHT): capital letters and digits,
            starting with a letter. It can&apos;t be changed later.
          </span>
        </label>
        {field("bot_name", "Chatbot name", "e.g. Mira")}
        <label className="tm-field full">
          Copy setup from
          <select
            className="f"
            value={form.copy_from}
            onChange={set("copy_from")}
          >
            {clinics.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.id})
              </option>
            ))}
          </select>
          <span className="tm-hint">
            Copies hours, slots, canvas, Appearance, Templates and Menu wording.
            Not its contact details, services, doctors, websites or keys.
          </span>
        </label>
        {field("phone", "Phone", "+919876543210")}
        {field("whatsapp", "WhatsApp", "+919876543210")}
        {field("website", "Website", "https://clinic-website.com", true)}
        {field("manager_name", "First admin's name (optional)")}
        {field("manager_email", "First admin's email (optional)")}
      </div>
      {error && (
        <div className="warnbox" role="alert" style={{ marginTop: 12 }}>
          {error}
        </div>
      )}
      <div className="tm-actions" style={{ marginTop: 16 }}>
        <button type="button" className="btn g" onClick={onClose}>
          Cancel
        </button>
        <button type="submit" className="btn" disabled={busy || !ready}>
          {busy ? "Adding…" : "Add clinic"}
        </button>
      </div>
    </form>
  );
}
