/**
 * My Receipts Page — user's own reimbursement list with date search.
 */

var currentPage = 1;
var currentDate = '';
var PAGE_SIZE = 20;

var OCR_STATUS_MAP = { 0: '待处理', 1: '已提取', '-1': '提取失败' };

// ── Init ─────────────────────────────────────────────────
guardAuth();
initNav();

// ── Search ───────────────────────────────────────────────
function searchByDate() {
  currentDate = document.getElementById('searchDate').value;
  currentPage = 1;
  loadReceipts();
}

function clearSearch() {
  document.getElementById('searchDate').value = '';
  currentDate = '';
  currentPage = 1;
  loadReceipts();
}

// ── Load ─────────────────────────────────────────────────
async function loadReceipts() {
  var listEl = document.getElementById('receiptList');
  var emptyEl = document.getElementById('emptyState');
  var pagEl = document.getElementById('pagination');

  listEl.innerHTML = '<div style="text-align:center;padding:40px;color:#94a3b8;">⏳ 加载中...</div>';
  pagEl.style.display = 'none'; emptyEl.style.display = 'none';
  hideStatus();

  var url = '/api/my-receipts?page=' + currentPage + '&page_size=' + PAGE_SIZE;
  if (currentDate) { url += '&date=' + encodeURIComponent(currentDate); }

  try {
    var resp = await fetch(url, { headers: authHeaders() });
    var json = await resp.json();

    if (!resp.ok || json.code !== 0) {
      showStatus('error', json.msg || '加载失败');
      listEl.innerHTML = ''; emptyEl.style.display = 'block';
      return;
    }

    var receipts = json.data || [];
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

// ── Render ───────────────────────────────────────────────
function renderCard(r, idx) {
  var created = fmtDate(r.created_at);
  var time = fmtTime(r.created_at);
  var merchant = r.merchant || '（未识别商户）';
  var typeLabel = r.expense_type || '其他';
  var amount = fmtAmount(r.total_amount);
  var ocrStatus = OCR_STATUS_MAP[r.status] || ('状态' + r.status);

  return '<div class="receipt-card" id="card-' + idx + '" onclick="toggleCard(' + idx + ')">' +
    '<div class="receipt-row">' +
      '<div class="col-date">' + created + '<br><small>' + time + '</small></div>' +
      '<div class="col-merchant">' + escHtml(merchant) + '</div>' +
      '<div class="col-type">' + escHtml(typeLabel) + '</div>' +
      '<div class="col-amount">¥' + amount + '</div>' +
      '<div class="col-status">' + statusBadge(r.approval_status) + '</div>' +
      '<div class="col-arrow">▼</div>' +
    '</div>' +
    '<div class="receipt-detail">' +
      '<div class="detail-grid">' +
        '<div class="detail-item"><span class="d-label">报销人</span><span class="d-value">' + escHtml(r.applicant || '-') + '</span></div>' +
        '<div class="detail-item"><span class="d-label">参与人数</span><span class="d-value">' + (r.head_count || 1) + ' 人</span></div>' +
        '<div class="detail-item"><span class="d-label">报销类型</span><span class="d-value">' + escHtml(r.expense_type || '-') + '</span></div>' +
        '<div class="detail-item"><span class="d-label">OCR 状态</span><span class="d-value">' + ocrStatus + '</span></div>' +
        '<div class="detail-item"><span class="d-label">审批状态</span><span class="d-value">' + statusBadge(r.approval_status) + '</span></div>' +
        '<div class="detail-item"><span class="d-label">任务 UUID</span><span class="d-value" style="font-size:11px;font-family:monospace;">' + r.uuid + '</span></div>' +
        (r.error_message ? '<div class="detail-item full"><span class="d-label">错误信息</span><span class="d-value" style="color:#dc2626;">' + escHtml(r.error_message) + '</span></div>' : '') +
        (r.ocr_raw_text ? '<div class="detail-item full"><span class="d-label">OCR 原始文本</span><div class="ocr-raw" style="margin-top:4px;padding:10px 12px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;font-size:12px;color:#64748b;white-space:pre-wrap;max-height:120px;overflow-y:auto;font-family:monospace;">' + escHtml(r.ocr_raw_text) + '</div></div>' : '') +
      '</div>' +
    '</div>' +
  '</div>';
}

function toggleCard(idx) {
  var card = document.getElementById('card-' + idx);
  if (!card) return;
  document.querySelectorAll('.receipt-card.expanded').forEach(function (c) {
    if (c !== card) c.classList.remove('expanded');
  });
  card.classList.toggle('expanded');
}

// ── Pagination ───────────────────────────────────────────
function goPage(p) {
  currentPage = p;
  loadReceipts();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ── Load ─────────────────────────────────────────────────
loadReceipts();
