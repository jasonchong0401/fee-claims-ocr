/**
 * Fee Claims — Shared JavaScript
 * Auth guard, navigation, dropdown, profile/password modals, helpers.
 */

// ── Auth ─────────────────────────────────────────────────
const TOKEN = localStorage.getItem('token');
const USERNAME = localStorage.getItem('username');
const ROLE = localStorage.getItem('role');
const EMPLOYEE_ID = localStorage.getItem('employee_id');

/** Redirect to /login if not authenticated. Call on pages that require login. */
function guardAuth() {
  if (!TOKEN) { window.location.href = '/'; }
}

/** Redirect to /upload if not admin. Call on admin-only pages (after guardAuth). */
function guardAdmin() {
  if (ROLE !== 'admin') { window.location.href = '/upload'; }
}

// ── Nav Bar ──────────────────────────────────────────────
function initNav() {
  const elUser = document.getElementById('displayUsername');
  const elRole = document.getElementById('displayRole');
  if (elUser) elUser.textContent = USERNAME || '-';
  if (elRole) {
    elRole.textContent = ROLE || '';
    elRole.className = 'role-tag ' + (ROLE === 'admin' ? 'admin' : 'user');
  }
  // Show admin nav link if applicable
  const adminLink = document.getElementById('navAdminReview');
  if (adminLink && ROLE === 'admin') {
    adminLink.style.display = '';
  }
}

// ── Dropdown ─────────────────────────────────────────────
function toggleDropdown() {
  document.getElementById('dropdown').classList.toggle('show');
}
document.addEventListener('click', function (e) {
  if (!e.target.closest('.right-section')) {
    const dd = document.getElementById('dropdown');
    if (dd) dd.classList.remove('show');
  }
});

// ── Profile Modal ────────────────────────────────────────
async function openProfileModal() {
  const dd = document.getElementById('dropdown');
  if (dd) dd.classList.remove('show');
  try {
    const resp = await fetch('/api/me', { headers: authHeaders() });
    const json = await resp.json();
    if (json.code === 0 && json.data) {
      const d = json.data;
      setVal('pfUsername', d.username);
      setVal('pfEmployeeId', d.employee_id);
      setVal('pfRole', d.role);
      setVal('pfDept', d.department);
      setVal('pfEmail', d.email);
      setVal('pfStartDate', d.start_date);
    }
  } catch (e) { /* ignore */ }
  showModal('profileModal');
}

function closeProfileModal() { hideModal('profileModal'); }

async function saveProfile() {
  const body = {
    email: getVal('pfEmail') || null,
    department: getVal('pfDept') || null,
  };
  try {
    const resp = await fetch('/api/me', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(body),
    });
    const json = await resp.json();
    if (json.code === 0) {
      closeProfileModal();
      showStatus('success', '个人信息已更新');
    }
  } catch (e) { showStatus('error', '保存失败'); }
}

// ── Password Modal ───────────────────────────────────────
function openPasswordModal() {
  const dd = document.getElementById('dropdown');
  if (dd) dd.classList.remove('show');
  setVal('pwOld', ''); setVal('pwNew', ''); setVal('pwConfirm', '');
  clearPwMsg();
  showModal('passwordModal');
}

function closePasswordModal() { hideModal('passwordModal'); }

async function changePassword() {
  const oldPw = getVal('pwOld');
  const newPw = getVal('pwNew');
  const confirm = getVal('pwConfirm');

  if (!oldPw || !newPw) { pwError('请填写所有字段'); return; }
  if (newPw.length < 6) { pwError('新密码至少6位'); return; }
  if (newPw !== confirm) { pwError('两次新密码不一致'); return; }

  try {
    const resp = await fetch('/api/me/password', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ old_password: oldPw, new_password: newPw }),
    });
    const json = await resp.json();
    if (json.code === 0) {
      const msg = document.getElementById('pwMsg');
      if (msg) { msg.className = 'status-msg show success'; msg.textContent = '密码修改成功'; }
      setTimeout(closePasswordModal, 1200);
    } else {
      pwError(json.msg || '修改失败');
    }
  } catch (e) { pwError('网络异常'); }
}

function pwError(text) {
  const msg = document.getElementById('pwMsg');
  if (msg) { msg.className = 'status-msg show error'; msg.textContent = text; }
}
function clearPwMsg() {
  const msg = document.getElementById('pwMsg');
  if (msg) { msg.className = 'status-msg'; msg.textContent = ''; }
}

// ── Logout ───────────────────────────────────────────────
function logout() {
  localStorage.removeItem('token');
  localStorage.removeItem('username');
  localStorage.removeItem('employee_id');
  localStorage.removeItem('role');
  window.location.href = '/';
}

// ── Helpers ──────────────────────────────────────────────
function authHeaders() {
  return { 'Authorization': 'Bearer ' + TOKEN };
}

function showStatus(type, msg) {
  const el = document.getElementById('statusMsg');
  if (el) { el.className = 'status-msg show ' + type; el.textContent = msg; }
}
function hideStatus() {
  const el = document.getElementById('statusMsg');
  if (el) { el.className = 'status-msg'; el.textContent = ''; }
}

function escHtml(s) {
  if (!s) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function getVal(id) {
  const el = document.getElementById(id);
  return el ? el.value.trim() : '';
}
function setVal(id, val) {
  const el = document.getElementById(id);
  if (el) el.value = val || '';
}

function showModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add('show');
}
function hideModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove('show');
}

/** Status badge HTML given approval_status value. */
function statusBadge(approvalStatus) {
  const map = {
    pending:        { label: '审批中', cls: 'badge pending' },
    approved:       { label: '已通过', cls: 'badge approved' },
    rejected:       { label: '已拒绝', cls: 'badge rejected' },
    pending_update: { label: '待更新', cls: 'badge pending_update' },
  };
  const s = map[approvalStatus] || { label: approvalStatus || '未知', cls: 'badge' };
  return '<span class="' + s.cls + '">' + s.label + '</span>';
}

/** Format YYYY-MM-DD from ISO string. */
function fmtDate(iso) { return iso ? iso.slice(0, 10) : '-'; }
/** Format HH:MM from ISO string. */
function fmtTime(iso) { return iso ? iso.slice(11, 16) : ''; }
/** Format float to 2 decimal places. */
function fmtAmount(n) { return n != null ? Number(n).toFixed(2) : '-.--'; }

/** Render pagination controls. */
function renderPagination(containerId, total, currentPage, pageSize, onPageChange) {
  const pagEl = document.getElementById(containerId);
  if (!pagEl) return;
  const totalPages = Math.ceil(total / pageSize);
  if (totalPages <= 1) { pagEl.style.display = 'none'; return; }
  pagEl.style.display = 'flex';

  let html = '<button class="btn-page" ' + (currentPage <= 1 ? 'disabled' : '') +
    ' onclick="' + onPageChange + '(' + (currentPage - 1) + ')">‹ 上一页</button>';

  const maxB = 5;
  let s = Math.max(1, currentPage - Math.floor(maxB / 2));
  let e = Math.min(totalPages, s + maxB - 1);
  if (e - s < maxB - 1) s = Math.max(1, e - maxB + 1);

  if (s > 1) {
    html += '<button class="btn-page" onclick="' + onPageChange + '(1)">1</button>';
    if (s > 2) html += '<span class="page-info">...</span>';
  }
  for (let p = s; p <= e; p++) {
    html += '<button class="btn-page' + (p === currentPage ? ' active' : '') +
      '" onclick="' + onPageChange + '(' + p + ')">' + p + '</button>';
  }
  if (e < totalPages) {
    if (e < totalPages - 1) html += '<span class="page-info">...</span>';
    html += '<button class="btn-page" onclick="' + onPageChange + '(' + totalPages + ')">' + totalPages + '</button>';
  }
  html += '<button class="btn-page" ' + (currentPage >= totalPages ? 'disabled' : '') +
    ' onclick="' + onPageChange + '(' + (currentPage + 1) + ')">下一页 ›</button>';
  pagEl.innerHTML = html;
}
