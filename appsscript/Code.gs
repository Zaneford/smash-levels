/**
 * Smash levels sheet endpoint.
 *
 * Bound to the SMASH spreadsheet (Extensions > Apps Script).
 * Deploy as: Web app, execute as Me, access "Anyone".
 *
 * Before first use, set the shared secret:
 *   Project Settings > Script Properties > add SECRET = <same value as
 *   the SHEET_WEBHOOK_SECRET repo secret>
 *
 * IMPORTANT: every code change needs a NEW deployment version, or the
 * live URL keeps serving the old code. Deploy > Manage deployments >
 * edit > Version: New version.
 */

var SHEET_NAME  = 'Sheet1';  // tab the ES importer study reads
var FIRST_ROW   = 2;         // row 1 is the header
var LAST_ROW    = 60;        // cleared on every write
var NUM_COLS    = 7;

// Separate spreadsheet for VIX levels. Not a secret -- just an id.
// Set VIX_SPREADSHEET_ID to '' to disable VIX writes entirely.
var VIX_SPREADSHEET_ID = '1ga41JlWH2wUX0kg_nHfqkRZwsg7DlQ3Hu82i3TcuuNM';
var VIX_SHEET_NAME     = 'VIX SR';
var VIX_LAST_ROW       = 20;

function props_() {
  return PropertiesService.getScriptProperties();
}

function json_(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

/**
 * Clear a block and write rows into it. Returns the number written.
 * Pads ragged rows so setValues() cannot throw halfway through.
 */
function writeRows_(sheet, rows, lastRow) {
  var padded = rows.map(function (r) {
    var out = r.slice(0, NUM_COLS);
    while (out.length < NUM_COLS) out.push('');
    return out;
  });
  sheet.getRange(FIRST_ROW, 1, lastRow - FIRST_ROW + 1, NUM_COLS).clearContent();
  if (padded.length) {
    sheet.getRange(FIRST_ROW, 1, padded.length, NUM_COLS).setValues(padded);
  }
  return padded.length;
}

/**
 * Freshness probe for the heartbeat workflow.
 * GET ?secret=...  ->  {plan_date, last_write, age_hours}
 */
function doGet(e) {
  var secret = props_().getProperty('SECRET');
  if (!secret || !e.parameter || e.parameter.secret !== secret) {
    return json_({error: 'unauthorized'});
  }

  var last = props_().getProperty('last_write_iso');
  if (!last) {
    return json_({plan_date: null, last_write: null, age_hours: 999});
  }

  var ageHours = (new Date().getTime() - new Date(last).getTime()) / 3600000;
  return json_({
    plan_date:  props_().getProperty('last_plan_date'),
    last_write: last,
    age_hours:  Math.round(ageHours * 10) / 10
  });
}

/**
 * Write endpoint.
 * POST {secret, plan_date, rows: [[...]], vix_rows: [[...]]}
 *
 * rows     -> the bound spreadsheet (ES levels)
 * vix_rows -> VIX_SPREADSHEET_ID (optional; omitted or empty = leave alone)
 */
function doPost(e) {
  var secret = props_().getProperty('SECRET');
  if (!secret) return json_({error: 'SECRET script property not set'});

  var body;
  try {
    body = JSON.parse(e.postData.contents);
  } catch (err) {
    return json_({error: 'invalid JSON'});
  }

  if (body.secret !== secret) return json_({error: 'unauthorized'});

  var rows = body.rows;
  if (!Array.isArray(rows) || rows.length === 0) {
    return json_({error: 'no rows'});
  }
  if (rows.length > (LAST_ROW - FIRST_ROW + 1)) {
    return json_({error: 'too many rows'});
  }

  var vixRows = Array.isArray(body.vix_rows) ? body.vix_rows : [];
  if (vixRows.length > (VIX_LAST_ROW - FIRST_ROW + 1)) {
    return json_({error: 'too many vix rows'});
  }

  // Idempotency. Retries and manual replays all land here; none of them
  // should write twice. Governs both spreadsheets together.
  if (body.plan_date && props_().getProperty('last_plan_date') === body.plan_date) {
    return json_({status: 'duplicate', plan_date: body.plan_date});
  }

  var sheet = SpreadsheetApp.getActive().getSheetByName(SHEET_NAME);
  if (!sheet) return json_({error: 'sheet "' + SHEET_NAME + '" not found'});

  var lock = LockService.getScriptLock();
  try {
    lock.waitLock(20000);
  } catch (err) {
    return json_({error: 'busy'});
  }

  try {
    var written = writeRows_(sheet, rows, LAST_ROW);
    SpreadsheetApp.flush();

    // VIX is secondary. If it fails, the ES levels are already safely
    // written -- report the problem rather than failing the whole call.
    var vixWritten = 0;
    var vixError   = null;
    if (vixRows.length && VIX_SPREADSHEET_ID) {
      try {
        var vixSheet = SpreadsheetApp.openById(VIX_SPREADSHEET_ID)
                                    .getSheetByName(VIX_SHEET_NAME);
        if (!vixSheet) {
          vixError = 'vix tab "' + VIX_SHEET_NAME + '" not found';
        } else {
          vixWritten = writeRows_(vixSheet, vixRows, VIX_LAST_ROW);
          SpreadsheetApp.flush();
        }
      } catch (err) {
        vixError = String(err);
      }
    }

    props_().setProperties({
      last_plan_date: body.plan_date || '',
      last_write_iso: new Date().toISOString()
    });

    var out = {
      status: 'ok',
      rows: written,
      vix_rows: vixWritten,
      plan_date: body.plan_date
    };
    if (vixError) out.vix_error = vixError;
    return json_(out);
  } catch (err) {
    return json_({error: String(err)});
  } finally {
    lock.releaseLock();
  }
}

/**
 * Run once from the editor to authorise the script and self-test.
 * Writes a dummy row to each spreadsheet, then clears both. Running this
 * after adding VIX_SPREADSHEET_ID triggers the extra permission prompt
 * for reaching a spreadsheet outside the bound one.
 */
function testWrite() {
  var sheet = SpreadsheetApp.getActive().getSheetByName(SHEET_NAME);
  if (!sheet) throw new Error('sheet "' + SHEET_NAME + '" not found');
  sheet.getRange(FIRST_ROW, 1, 1, NUM_COLS)
       .setValues([[7654, '', 'TEST', 'yellow', 1, 3, 1]]);

  var vixSheet = null;
  if (VIX_SPREADSHEET_ID) {
    vixSheet = SpreadsheetApp.openById(VIX_SPREADSHEET_ID)
                             .getSheetByName(VIX_SHEET_NAME);
    if (!vixSheet) throw new Error('vix tab "' + VIX_SHEET_NAME + '" not found');
    vixSheet.getRange(FIRST_ROW, 1, 1, NUM_COLS)
            .setValues([[17.92, '', 'TEST', 'red', 0, 2, 2]]);
  }

  SpreadsheetApp.flush();
  Utilities.sleep(2000);

  sheet.getRange(FIRST_ROW, 1, 1, NUM_COLS).clearContent();
  if (vixSheet) vixSheet.getRange(FIRST_ROW, 1, 1, NUM_COLS).clearContent();
  Logger.log('ok');
}
