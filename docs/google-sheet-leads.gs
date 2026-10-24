// ===================== NEO CRM: send Meta lead rows to the CRM =====================
// Paste this block at the END of the sheet's existing Apps Script (Extensions > Apps Script).
// It does not change the existing code; every name here starts with "crm" to avoid clashes.
//
// One-time setup:
//  1. Fill CRM_CONFIG below (backend address, clinic code, the tab that Meta fills).
//  2. Project Settings (gear icon) > Script properties > Add: CRM_SECRET = the SHEET_WEBHOOK_SECRET value
//     from backend/.env. (Kept out of the code so the secret is not visible to people who view the script.)
//  3. Select the function "crmSetup" and press Run once; allow the permissions Google asks for.
//     It adds a "CRM" column and runs crmSend every 5 minutes from then on.
//
// Every 5 minutes, each row whose CRM cell is empty, or which changed since it was sent, goes to the CRM.
// The CRM cell then shows the lead code, e.g. "CL01-00012 ✓", or the reason it was not accepted.
// Rows Meta adds do not fire edit triggers (Google only fires them for people), so a timer is used.

const CRM_CONFIG = {
  url: "https://YOUR-BACKEND-ADDRESS/v1/integrations/sheet-leads",
  clinic: "CL01", // Neo Follicle
  tab: "", // the tab Meta writes to; "" = the first tab
  column: "CRM", // the status column added after the last header
  perRun: 50, // rows sent per run at most (the rest follow 5 minutes later)
};

function crmSetup() {
  ScriptApp.getProjectTriggers()
    .filter((t) => t.getHandlerFunction() === "crmSend")
    .forEach((t) => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger("crmSend").timeBased().everyMinutes(5).create();
  crmSend();
}

function crmSend() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(1000)) return; // the previous run is still going
  try {
    const secret = PropertiesService.getScriptProperties().getProperty("CRM_SECRET");
    if (!secret) throw new Error("Add CRM_SECRET in Project Settings > Script properties.");
    const book = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = CRM_CONFIG.tab ? book.getSheetByName(CRM_CONFIG.tab) : book.getSheets()[0];
    const values = sheet.getDataRange().getValues();
    if (values.length < 2) return;
    const headers = values[0].map((h) => String(h).trim());
    let col = headers.indexOf(CRM_CONFIG.column);
    if (col === -1) {
      col = headers.length;
      sheet.getRange(1, col + 1).setValue(CRM_CONFIG.column).setFontWeight("bold");
    }
    const status = sheet.getRange(2, col + 1, values.length - 1, 1);
    const cells = status.getValues();
    const notes = status.getNotes(); // each sent row's fingerprint, to notice later edits
    let sent = 0;
    for (let i = 1; i < values.length && sent < CRM_CONFIG.perRun; i++) {
      const row = {};
      headers.forEach((h, j) => {
        if (h && j !== col && values[i][j] !== "") row[h] = values[i][j] instanceof Date ? values[i][j].toISOString() : String(values[i][j]);
      });
      if (!Object.keys(row).length) continue; // empty row
      const print = Utilities.base64Encode(Utilities.computeDigest(Utilities.DigestAlgorithm.MD5, JSON.stringify(row)));
      const cell = String(cells[i - 1][0]);
      const code = (cell.match(/^CL\d{2}-\d+/) || [""])[0];
      if (code && cell.indexOf("✓") !== -1 && notes[i - 1][0] === print) continue; // sent, unchanged
      sent++;
      const res = UrlFetchApp.fetch(CRM_CONFIG.url, {
        method: "post",
        contentType: "application/json",
        muteHttpExceptions: true,
        payload: JSON.stringify({ clinic: CRM_CONFIG.clinic, secret: secret, sheet: sheet.getName(), row_number: i + 1, lead_code: code || null, row: row }),
      });
      let body = {};
      try {
        body = JSON.parse(res.getContentText());
      } catch (e) {}
      if (res.getResponseCode() === 200) {
        cells[i - 1][0] = body.lead_code + " ✓";
        notes[i - 1][0] = print;
      } else {
        cells[i - 1][0] = (code ? code + " " : "") + "✗ " + (body.detail || "Error " + res.getResponseCode());
        notes[i - 1][0] = ""; // tried again next run
      }
    }
    status.setValues(cells);
    status.setNotes(notes);
  } finally {
    lock.releaseLock();
  }
}
// =================== end of NEO CRM block ===================
