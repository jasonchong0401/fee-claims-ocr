/**
 * Admin Review Page — approve / reject / request-update on receipts.
 */

var currentTab = 'pending';
var currentPage = 1;
var PAGE_SIZE = 10;

// ── Init ─────────────────────────────────────────────────
guardAuth();
guardAdmin();
initNav();

// ── Tab Switch ───────────────────────────────────────────
function switchTab(status) {
  currentTab = status;
  currentPage = 1;
  document.querySelectorAll('.filter-tab').forEach(function (t) {
    t.classList.toggle('active', t.dataset.status === status);
  });
  loadReviews();
}

// ── Load Reviews ─────────────────────────────────────────
async function loadReviews() {
  var listEl = document.getElementById('reviewList');
  var emptyEl = document.getElementById('emptyState');
  var pagEl = document.getElementById('pagination');

  listEl.innerHTML = '<div style="text-align:center;padding:40px;color:#94a3b8;">⏳ 加载中...</div>';
  pagEl.style.display = 'none'; emptyEl.style.display = 'none';
  hideStatus();

  var url = '/api/admin/review-queue?approval_status=' + currentTab + '&page=' + currentPage + '&page_size=' + PAGE_SIZE;

  try {
    var resp = await fetch(url, { headers: authHeaders() });
    var json = await resp.json();
    if (!resp.ok || json.code !== 0) {
      showStatus('error', json.msg || '加载失败');
      listEl.innerHTML = ''; emptyEl.style.display = 'block';
      return;
    }

    var receipts = json.data || [];
    updateCounts();

    if (receipts.length === 0) {
      listEl.innerHTML = ''; emptyEl.style.display = 'block';
      return;
    }

    listEl.innerHTML = receipts.map(function (r, i) { return renderCard(r, i); }).join('');
    renderPagination('pagination', json.total || 0, currentPage, PAGE_SIZE, 'goPage');
  } catch (err) {
    showStatus('error', '网络异常：' + err.message);
    listEl.innerHTML = ''; emptyEl.style.display = 'block';
  }
}

// ── Update Counts ────────────────────────────────────────
async function updateCounts() {
  var statuses = ['pending', 'approved', 'rejected', 'pending_update'];
  statuses.forEach(async function (s) {
    try {
      var resp = await fetch('/api/admin/review-queue?approval_status=' + s + '&page_size=1', {
        headers: authHeaders()
      });
      var json = await resp.json();
      var cap = s.charAt(0).toUpperCase() + s.slice(1).replace('_', '');
      var el = document.getElementById('count' + cap);
      if (el) el.textContent = json.total || 0;
    } catch (e) {}
  });
}

// ── Render Card ──────────────────────────────────────────
function renderCard(r, idx) {
  var created = fmtDate(r.created_at);
  var time = fmtTime(r.created_at);
  var amount = fmtAmount(r.total_amount);
  var ocrStatus = ({ 0: '待处理', 1: '已提取', '-1': '提取失败' })[r.status] || ('状态' + r.status);
  var statusLabel = ({ pending: '审批中', approved: '已通过', rejected: '已拒绝', pending_update: '待更新' })[r.approval_status] || r.approval_status;

  // Image URL
  var imgHtml = '<div class="no-img">📷<br>无票据图片</div>';
  if (r.image_path) {
    var imgUrl = '/uploads/' + r.image_path.replace(/^uploads\/receipts\//, '');
    imgHtml = '<img src="' + escHtml(imgUrl) + '" alt="票据图片" onclick="event.stopPropagation();openImage(\'' + escHtml(imgUrl) + '\')" onerror="this.parentElement.innerHTML=\'<div class=no-img>📷<br>图片加载失败</div>\'">';
  }

  var actionBar = '';
  if (currentTab === 'pending') {
    actionBar = '<div class="action-bar">' +
      '<div class="comment-box">' +
        '<textarea id="comment-' + idx + '" placeholder="输入审批意见（可选）..."></textarea>' +
      '</div>' +
      '<button class="btn btn-approve btn-lg" id="btnApprove-' + idx + '" onclick="doApprove(\'' + r.uuid + '\', \'approved\', ' + idx + ')">' +
        '<span class="spinner" id="spinApprove-' + idx + '"></span>✅ 批准</button>' +
      '<button class="btn btn-update btn-lg" id="btnUpdate-' + idx + '" onclick="doApprove(\'' + r.uuid + '\', \'pending_update\', ' + idx + ')">' +
        '<span class="spinner" id="spinUpdate-' + idx + '"></span>📝 需修改</button>' +
      '<button class="btn btn-reject btn-lg" id="btnReject-' + idx + '" onclick="doApprove(\'' + r.uuid + '\', \'rejected\', ' + idx + ')">' +
        '<span class="spinner" id="spinReject-' + idx + '"></span>❌ 拒绝</button>' +
    '</div>';
  }

  return '<div class="review-card" id="card-' + idx + '">' +
    '<div class="card-body">' +
      '<div class="card-image">' + imgHtml + '</div>' +
      '<div class="card-fields">' +
        '<div class="field-row"><span class="f-label">状态</span><span class="f-value"><span class="badge ' + r.approval_status + '">' + statusLabel + '</span></span></div>' +
        '<div class="field-row"><span class="f-label">报销人</span><span class="f-value">' + escHtml(r.applicant || '-') + '</span></div>' +
        '<div class="field-row"><span class="f-label">类型</span><span class="f-value">' + escHtml(r.expense_type || '-') + '</span></div>' +
        '<div class="field-row"><span class="f-label">商户</span><span class="f-value">' + escHtml(r.merchant || '-') + '</span></div>' +
        '<div class="field-row"><span class="f-label">金额</span><span class="f-value amount">¥' + amount + '</span></div>' +
        '<div class="field-row"><span class="f-label">人数</span><span class="f-value">' + (r.head_count || 1) + ' 人</span></div>' +
        '<div class="field-row"><span class="f-label">提交人</span><span class="f-value">' + escHtml(r.employee_id || '-') + '</span></div>' +
        '<div class="field-row"><span class="f-label">提交时间</span><span class="f-value">' + created + ' ' + time + '</span></div>' +
        '<div class="field-row"><span class="f-label">OCR</span><span class="f-value">' + ocrStatus + '</span></div>' +
        '<div class="field-row"><span class="f-label">UUID</span><span class="f-value" style="font-size:11px;font-family:monospace;">' + r.uuid + '</span></div>' +
        (r.error_message ? '<div class="field-row"><span class="f-label">错误</span><span class="f-value error">' + escHtml(r.error_message) + '</span></div>' : '') +
        (r.review_comment ? '<div class="field-row"><span class="f-label">审批意见</span><span class="f-value" style="color:#16a34a;">' + escHtml(r.review_comment) + '</span></div>' : '') +
        (r.ocr_raw_text ? '<details class="ocr-block"><summary>OCR 原始文本</summary>' + escHtml(r.ocr_raw_text) + '</details>' : '') +
      '</div>' +
    '</div>' +
    actionBar +
  '</div>';
}

// ── Approve / Reject ─────────────────────────────────────
async function doApprove(uuid, status, idx) {
  var comment = document.getElementById('comment-' + idx);
  var commentText = comment ? comment.value.trim() : '';
  var card = document.getElementById('card-' + idx);

  var spinMap = { approved: 'Approve', rejected: 'Reject', pending_update: 'Update' };
  var spinId = 'spin' + spinMap[status] + '-' + idx;
  var spinEl = document.getElementById(spinId);
  if (spinEl) spinEl.classList.add('show');
  card.querySelectorAll('.btn').forEach(function (b) { b.disabled = true; });

  try {
    var resp = await fetch('/api/receipt/' + uuid + '/approve', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ approval_status: status, comment: commentText || null }),
    });
    var json = await resp.json();
    if (resp.ok && json.code === 0) {
      card.classList.add('done');
      setTimeout(function () { loadReviews(); }, 600);
      showStatus('success', '报销单已' + (status === 'approved' ? '批准' : status === 'rejected' ? '拒绝' : '标记为待更新'));
    } else {
      showStatus('error', json.msg || '操作失败');
      if (spinEl) spinEl.classList.remove('show');
      card.querySelectorAll('.btn').forEach(function (b) { b.disabled = false; });
    }
  } catch (err) {
    showStatus('error', '网络异常：' + err.message);
    if (spinEl) spinEl.classList.remove('show');
    card.querySelectorAll('.btn').forEach(function (b) { b.disabled = false; });
  }
}

// ── Image Modal ──────────────────────────────────────────
function openImage(url) {
  document.getElementById('imgModalSrc').src = url;
  document.getElementById('imgModal').classList.add('show');
}
// Click on modal backdrop closes it
document.getElementById('imgModal').addEventListener('click', function () {
  this.classList.remove('show');
});

// ── Pagination ───────────────────────────────────────────
function goPage(p) {
  currentPage = p;
  loadReviews();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ── Load ─────────────────────────────────────────────────
loadReviews();
