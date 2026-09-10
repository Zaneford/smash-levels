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

var SHEET_NAME  = 'Sheet1';  // tab the importer study reads
var FIRST_ROW   = 2;         // row 1 is the header
var LAST_ROW    = 60;        // cleared on every write
var NUM_COLS    = 7;

function props_() {
  return PropertiesService.getScriptProperties();
}

function json_(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
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
 * POST {secret, plan_date, rows: [[...7 cols...], ...]}
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

  // Idempotency. Polling, retries, and manual replays all land here;
  // none of them should write twice.
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
    // Normalise ragged rows so setValues() cannot throw mid-write.
    var padded = rows.map(function (r) {
      var out = r.slice(0, NUM_COLS);
      while (out.length < NUM_COLS) out.push('');
      return out;
    });

    sheet.getRange(FIRST_ROW, 1, LAST_ROW - FIRST_ROW + 1, NUM_COLS).clearContent();
    sheet.getRange(FIRST_ROW, 1, padded.length, NUM_COLS).setValues(padded);
    SpreadsheetApp.flush();

    props_().setProperties({
      last_plan_date: body.plan_date || '',
      last_write_iso: new Date().toISOString()
    });

    return json_({status: 'ok', rows: padded.length, plan_date: body.plan_date});
  } catch (err) {
    return json_({error: String(err)});
  } finally {
    lock.releaseLock();
  }
}

/**
 * Run once from the editor to authorise the script and self-test.
 * Writes a single dummy row, then clears it.
 */
function testWrite() {
  var sheet = SpreadsheetApp.getActive().getSheetByName(SHEET_NAME);
  if (!sheet) throw new Error('sheet "' + SHEET_NAME + '" not found');
  sheet.getRange(FIRST_ROW, 1, 1, NUM_COLS)
       .setValues([[7654, '', 'TEST', 'yellow', 1, 3, 1]]);
  SpreadsheetApp.flush();
  Utilities.sleep(2000);
  sheet.getRange(FIRST_ROW, 1, 1, NUM_COLS).clearContent();
  Logger.log('ok');
}
