// Apps Script 코드를 구글 서비스 흉내(가짜 객체)로 검사:  node tests/test_apps_script.js
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

function makeEnv() {
  const rows = [];
  const mails = [];
  const cache = {};
  const sheet = {
    getLastRow: () => rows.length,
    appendRow: r => rows.push(r.slice()),
    setFrozenRows() {}, getSheetId: () => 0,
    getRange(r, c, nr = 1, nc = 1) {
      return {
        setFontWeight() { return this; }, setBackground() { return this; }, setDataValidation() { return this; }, setNumberFormat() { return this; },
        getValues: () => rows.slice(r - 1, r - 1 + nr).map(x => x.slice(c - 1, c - 1 + nc)),
        setValue: v => { rows[r - 1][c - 1] = v; },
      };
    },
    getParent: () => ({ getUrl: () => "https://docs.google.com/spreadsheets/d/TEST" }),
  };
  const env = {
    console, Date, Math, JSON, Number, String, Object, isFinite,
    SpreadsheetApp: {
      getActiveSpreadsheet: () => ({ getSheetByName: () => sheet, insertSheet: () => sheet }),
      newDataValidation: () => ({ requireValueInList() { return this; }, setAllowInvalid() { return this; }, build: () => ({}) }),
    },
    CacheService: { getScriptCache: () => ({ get: k => cache[k], put: (k, v) => { cache[k] = v; } }) },
    LockService: { getScriptLock: () => ({ waitLock() {}, releaseLock() {} }) },
    MailApp: { sendEmail: m => mails.push(m) },
    Session: { getEffectiveUser: () => ({ getEmail: () => "me@gmail.com" }) },
    ContentService: { MimeType: { JSON: "json" }, createTextOutput: t => ({ text: t, setMimeType() { return this; } }) },
    ScriptApp: { getProjectTriggers: () => [] },
  };
  env.module = { exports: {} };
  vm.createContext(env);
  vm.runInContext(fs.readFileSync(path.join(__dirname, "..", "apps-script", "Code.gs"), "utf8"), env);
  return { env, rows, mails, api: env.module.exports };
}

const good = (o = {}) => Object.assign({ rid: "r1", biz: "1248100998", corp: "(주)테스트", ind: "제조업", emp: "120", sales: "350", pay: "",
  name: "홍길동", tel: "01012345678", mail: "a@b.co.kr", memo: "", agree: true, t: Date.now() - 10000 }, o);

let n = 0;
const t = (name, fn) => { fn(); n++; console.log("ok -", name); };

t("사업자번호 체크섬", () => {
  const { api } = makeEnv();
  assert.ok(api.bizNoValid("124-81-00998"));
  assert.ok(!api.bizNoValid("124-81-00999"));
});

t("필수값 오류", () => {
  const { api } = makeEnv();
  const v = api.validateLead({});
  assert.deepStrictEqual(Object.keys(v.errors).sort(), ["agree", "biz", "corp", "emp", "ind", "name", "tel"].sort());
});

t("정상 접수 → 시트 저장 + 메일 (연락처 미포함)", () => {
  const { api, rows, mails } = makeEnv();
  const r = api.handleLead_(good(), new Date());
  assert.strictEqual(r.ok, true);
  assert.strictEqual(rows.length, 2); // 머리글 + 1건
  assert.deepStrictEqual(rows[0], api.HEADERS);
  assert.strictEqual(rows[1][4], "124-81-00998");
  assert.strictEqual(rows[1][10], "'010-1234-5678");
  assert.strictEqual(rows[1][1], "신규");
  assert.strictEqual(mails.length, 1);
  assert.ok(mails[0].subject.includes("(주)테스트"));
  assert.ok(!mails[0].body.includes("010-1234-5678"));
  assert.strictEqual(mails[0].to, "me@gmail.com");
});

t("같은 접수번호 두 번 → 한 건만 저장", () => {
  const { api, rows } = makeEnv();
  api.handleLead_(good(), new Date());
  const r = api.handleLead_(good(), new Date());
  assert.strictEqual(r.duplicate, true);
  assert.strictEqual(rows.length, 2);
});

t("스팸: 숨은 입력칸, 너무 빠른 제출, 폭주", () => {
  const { api, rows } = makeEnv();
  assert.strictEqual(api.handleLead_(good({ website: "x" }), new Date()).ok, true);
  assert.strictEqual(rows.length, 0);
  assert.strictEqual(api.handleLead_(good({ t: Date.now() }), new Date()).ok, false);
  const now = new Date();
  for (let i = 0; i < api.CONFIG.MAX_PER_10MIN; i++) assert.strictEqual(api.handleLead_(good({ rid: "x" + i }), now).ok, true);
  assert.strictEqual(api.handleLead_(good({ rid: "over" }), now).ok, false);
});

t("검증 오류는 저장 안 함", () => {
  const { api, rows } = makeEnv();
  const r = api.handleLead_(good({ biz: "111-11-11111", agree: false }), new Date());
  assert.strictEqual(r.ok, false);
  assert.ok(r.errors.biz && r.errors.agree);
  assert.strictEqual(rows.length, 0);
});

t("보유기간 지난 건 개인정보 파기 (계약 건 제외)", () => {
  const { api, rows } = makeEnv();
  api.handleLead_(good({ rid: "a" }), new Date());
  api.handleLead_(good({ rid: "b" }), new Date());
  api.handleLead_(good({ rid: "c" }), new Date());
  const old = new Date(Date.now() - 400 * 86400000);
  rows[1][0] = old; rows[2][0] = old; rows[2][1] = "계약";
  assert.strictEqual(api.purgeOld(), 1);
  assert.strictEqual(rows[1][api.HEADERS.indexOf("연락처")], "파기");
  assert.strictEqual(rows[1][1], "종결");
  assert.strictEqual(rows[2][api.HEADERS.indexOf("연락처")], "'010-1234-5678");
  assert.strictEqual(rows[1][api.HEADERS.indexOf("회사명")], "(주)테스트");
});

console.log(`\n${n}개 통과`);
