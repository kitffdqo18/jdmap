/**
 * 중대재해 MAP 견적 접수 — 구글 스프레드시트 + Gmail 알림
 *
 * 설치 (안내서 4단계)
 *  1. 구글 드라이브에서 새 스프레드시트 만들기 → 확장 프로그램 → Apps Script
 *  2. 이 파일 내용을 전부 붙여 넣고 저장 → 아래 CONFIG 의 NOTIFY_TO 확인
 *  3. 함수 선택에서 setup 실행 → 권한 허용 (시트 머리글·자동 파기 예약·시험 메일)
 *  4. 배포 → 새 배포 → 유형 '웹 앱' → 실행 사용자 '나', 액세스 '모든 사용자' → 배포
 *  5. 나온 '웹 앱 URL'(…/exec)을 사이트 docs/config.js 의 leadEndpoint 에 붙여 넣기
 *  코드를 고친 뒤에는 배포 → 배포 관리 → 수정 → 버전 '새 버전' 으로 다시 배포해야 반영된다.
 */
var CONFIG = {
  SHEET_NAME: '접수',
  NOTIFY_TO: '',              // 비우면 이 스크립트를 만든 계정(본인 Gmail)으로 알림
  INCLUDE_PII_IN_MAIL: false, // true 면 메일에 연락처까지 표시 (기본: 회사명·업종·규모 + 시트 링크)
  RETENTION_DAYS: 365,        // 사이트 config.js 의 retentionDays 와 같게
  CONSENT_VERSION: '2026-10-v1',
  MIN_FILL_SECONDS: 3,
  MAX_PER_10MIN: 20           // 10분에 이보다 많이 들어오면 잠시 막음 (스팸 폭주 방지)
};

var HEADERS = ['접수시각', '상태', '담당메모', '회사명', '사업자번호', '업종', '상시근로자', '매출(억)', '총급여(억)',
               '담당자', '연락처', '이메일', '문의', '동의시각', '동의버전', '접수번호', '접수페이지'];
var PII_COLS = ['사업자번호', '담당자', '연락처', '이메일', '문의'];
var STATUSES = ['신규', '연락완료', '견적발송', '계약', '종결'];
var INDUSTRIES = ['건설업', '제조업', '운수·창고업', '도소매업', '숙박·음식점업', '사업서비스업', '농림어업', '광업', '기타'];

/* ---------- 입력 검증 (사이트 화면과 같은 규칙) ---------- */
function onlyDigits(s) { return String(s || '').replace(/\D/g, ''); }

function bizNoValid(v) {
  var d = onlyDigits(v);
  if (d.length !== 10) return false;
  var w = [1, 3, 7, 1, 3, 7, 1, 3, 5], s = 0;
  for (var i = 0; i < 9; i++) s += Number(d[i]) * w[i];
  s += Math.floor(Number(d[8]) * 5 / 10);
  return (10 - s % 10) % 10 === Number(d[9]);
}
function fmtBiz(v) { var d = onlyDigits(v); return d.length === 10 ? d.slice(0, 3) + '-' + d.slice(3, 5) + '-' + d.slice(5) : v; }
function fmtTel(v) {
  var d = onlyDigits(v);
  if (d.indexOf('02') === 0 && (d.length === 9 || d.length === 10)) return '02-' + d.slice(2, -4) + '-' + d.slice(-4);
  if (d.length === 10 || d.length === 11) return d.slice(0, 3) + '-' + d.slice(3, -4) + '-' + d.slice(-4);
  return v;
}
function num(v) {
  if (v === null || v === undefined || String(v).trim() === '') return { ok: true, v: '' };
  var n = Number(String(v).replace(/,/g, '').trim());
  return (isFinite(n) && n >= 0) ? { ok: true, v: n } : { ok: false };
}

function validateLead(d) {
  var e = {}, c = {};
  var s = function (k, n) { return String(d[k] === undefined || d[k] === null ? '' : d[k]).trim().slice(0, n || 200); };
  c.biz = s('biz', 20);
  if (!c.biz) e.biz = '사업자등록번호를 입력하세요.';
  else if (!bizNoValid(c.biz)) e.biz = '번호를 다시 확인하세요. 10자리 사업자등록번호 형식이 아닙니다.';
  else c.biz = fmtBiz(c.biz);
  c.corp = s('corp', 100); if (!c.corp) e.corp = '회사명을 입력하세요.';
  c.ind = s('ind', 30); if (INDUSTRIES.indexOf(c.ind) < 0) e.ind = '업종을 선택하세요.';
  var emp = num(d.emp);
  if (!emp.ok || emp.v === '' || emp.v < 1 || Math.floor(emp.v) !== emp.v) e.emp = '상시근로자 수를 1명 이상 숫자로 입력하세요.'; else c.emp = emp.v;
  var sales = num(d.sales); if (!sales.ok) e.sales = '숫자로 입력하세요. 단위는 억원입니다.'; else c.sales = sales.v;
  var pay = num(d.pay); if (!pay.ok) e.pay = '숫자로 입력하세요. 단위는 억원입니다.'; else c.pay = pay.v;
  c.name = s('name', 50); if (!c.name) e.name = '담당자명을 입력하세요.';
  c.tel = s('tel', 20); if (onlyDigits(c.tel).length < 9) e.tel = '연락 가능한 전화번호를 입력하세요.'; else c.tel = fmtTel(c.tel);
  c.mail = s('mail', 120); if (c.mail && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(c.mail)) e.mail = '이메일 형식을 확인하세요.';
  c.memo = s('memo', 2000);
  if (!(d.agree === true || String(d.agree).toLowerCase() === 'true')) e.agree = '개인정보 수집·이용에 동의해야 신청할 수 있습니다.';
  c.rid = s('rid', 64);
  c.page = s('page', 300);
  return { clean: c, errors: e };
}

/* ---------- 웹 앱 ---------- */
function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function doGet() { return json_({ ok: true, service: 'jdmap-leads' }); }

function doPost(e) {
  var d;
  try { d = JSON.parse((e && e.postData && e.postData.contents) || '{}'); }
  catch (err) { return json_({ ok: false, message: '요청 형식이 올바르지 않습니다.' }); }
  return json_(handleLead_(d, new Date()));
}

function handleLead_(d, now) {
  if (String(d.website || '').trim()) return { ok: true };                       // 숨은 입력칸(스팸 봇)
  var opened = Number(d.t || 0);
  if (opened && now.getTime() - opened < CONFIG.MIN_FILL_SECONDS * 1000) return { ok: false, message: '입력 내용을 확인한 뒤 다시 제출해 주세요.' };
  var v = validateLead(d);
  if (Object.keys(v.errors).length) return { ok: false, errors: v.errors, message: '입력 내용을 확인해 주세요.' };

  var cache = CacheService.getScriptCache();
  var bucket = 'n' + Math.floor(now.getTime() / 600000);
  var cnt = Number(cache.get(bucket) || 0);
  if (cnt >= CONFIG.MAX_PER_10MIN) return { ok: false, message: '신청이 많아 잠시 접수를 막았습니다. 10분 뒤 다시 시도해 주세요.' };

  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var sh = sheet_();
    var c = v.clean;
    if (c.rid && isDuplicate_(sh, c.rid)) return { ok: true, duplicate: true };  // 같은 신청이 두 번 온 경우
    var row = [now, '신규', '', c.corp, c.biz, c.ind, c.emp, c.sales, c.pay, c.name, "'" + c.tel, c.mail, c.memo,
               now, CONFIG.CONSENT_VERSION, c.rid, c.page];
    sh.appendRow(row);
    cache.put(bucket, String(cnt + 1), 900);
    try { notify_(c, sh); } catch (mailErr) { console.error('알림 메일 실패: ' + mailErr); }
    return { ok: true };
  } finally {
    lock.releaseLock();
  }
}

function sheet_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(CONFIG.SHEET_NAME);
  if (!sh) {
    sh = ss.insertSheet(CONFIG.SHEET_NAME);
  }
  if (sh.getLastRow() === 0) {
    sh.appendRow(HEADERS);
    sh.setFrozenRows(1);
    sh.getRange(1, 1, 1, HEADERS.length).setFontWeight('bold').setBackground('#F1F3F5');
    var rule = SpreadsheetApp.newDataValidation().requireValueInList(STATUSES, true).setAllowInvalid(false).build();
    sh.getRange(2, 2, 5000, 1).setDataValidation(rule);
    sh.getRange(2, 1, 5000, 1).setNumberFormat('yyyy-mm-dd hh:mm');
    sh.getRange(2, 14, 5000, 1).setNumberFormat('yyyy-mm-dd hh:mm');
  }
  return sh;
}

function isDuplicate_(sh, rid) {
  var last = sh.getLastRow();
  if (last < 2) return false;
  var col = HEADERS.indexOf('접수번호') + 1;
  var from = Math.max(2, last - 300);
  var vals = sh.getRange(from, col, last - from + 1, 1).getValues();
  for (var i = 0; i < vals.length; i++) if (String(vals[i][0]) === rid) return true;
  return false;
}

function notify_(c, sh) {
  var to = CONFIG.NOTIFY_TO || Session.getEffectiveUser().getEmail();
  if (!to) return;
  var url = sh.getParent().getUrl() + '#gid=' + sh.getSheetId();
  var lines = ['새 견적 의뢰가 접수되었습니다.', '',
    '회사명: ' + c.corp, '업종: ' + c.ind, '상시근로자: ' + c.emp + '명',
    '연 매출액: ' + (c.sales === '' ? '-' : c.sales + '억원'), '연간 총급여: ' + (c.pay === '' ? '-' : c.pay + '억원')];
  if (CONFIG.INCLUDE_PII_IN_MAIL) {
    lines.push('사업자번호: ' + c.biz, '담당자: ' + c.name, '연락처: ' + c.tel, '이메일: ' + (c.mail || '-'), '문의: ' + (c.memo || '-'));
  } else {
    lines.push('', '※ 담당자 연락처는 접수 시트에서 확인하세요.');
  }
  lines.push('', '접수 시트: ' + url);
  MailApp.sendEmail({ to: to, subject: '[중대재해 MAP] 견적 의뢰 · ' + c.corp + ' (' + c.ind + ', ' + c.emp + '명)', body: lines.join('\n') });
}

/* ---------- 설치·운영 ---------- */
function setup() {
  var sh = sheet_();
  ScriptApp.getProjectTriggers().forEach(function (t) { if (t.getHandlerFunction() === 'purgeOld') ScriptApp.deleteTrigger(t); });
  ScriptApp.newTrigger('purgeOld').timeBased().everyDays(1).atHour(3).create();
  var to = CONFIG.NOTIFY_TO || Session.getEffectiveUser().getEmail();
  MailApp.sendEmail(to, '[중대재해 MAP] 접수 알림 설정 완료', '이 메일이 보이면 견적 의뢰 알림이 정상적으로 설정된 것입니다.\n접수 시트: ' + sh.getParent().getUrl());
  console.log('설정 완료. 알림 받는 주소: ' + to);
}

/** 보유기간이 지난 신청의 개인정보 칸을 '파기'로 바꾼다 (계약 건 제외). 매일 03시 자동 실행. */
function purgeOld() {
  var sh = sheet_();
  var last = sh.getLastRow();
  if (last < 2) return 0;
  var data = sh.getRange(2, 1, last - 1, HEADERS.length).getValues();
  var cutoff = new Date(Date.now() - CONFIG.RETENTION_DAYS * 86400000);
  var piiIdx = PII_COLS.map(function (h) { return HEADERS.indexOf(h); });
  var n = 0;
  for (var i = 0; i < data.length; i++) {
    var r = data[i];
    if (!(r[0] instanceof Date) || r[0] >= cutoff || r[1] === '계약' || r[HEADERS.indexOf('담당자')] === '파기') continue;
    piiIdx.forEach(function (j) { sh.getRange(i + 2, j + 1).setValue('파기'); });
    sh.getRange(i + 2, 2).setValue('종결');
    n++;
  }
  console.log('개인정보 파기: ' + n + '건');
  return n;
}

if (typeof module !== 'undefined') {
  module.exports = { validateLead: validateLead, bizNoValid: bizNoValid, handleLead_: handleLead_, purgeOld: purgeOld, CONFIG: CONFIG, HEADERS: HEADERS };
}
