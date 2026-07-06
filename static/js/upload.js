/**
 * Upload Page — OCR image upload & field editing.
 */

// ── State ────────────────────────────────────────────────
let currentTaskUuid = null;
let originalOcrData = {};

// ── DOM refs ─────────────────────────────────────────────
const uploadZone   = document.getElementById('uploadZone');
const defaultState = document.getElementById('defaultState');
const previewRow   = document.getElementById('previewRow');
const previewImg   = document.getElementById('previewImg');
const fileInput    = document.getElementById('fileInput');
const rawToggle    = document.getElementById('rawToggle');
const rawText      = document.getElementById('rawText');
const taskUuidDisp = document.getElementById('taskUuidDisplay');
const formCard     = document.getElementById('formCard');
const btnSubmit    = document.getElementById('btnSubmit');
const spinnerSubmit = document.getElementById('spinnerSubmit');

const fields = {
  applicant:    document.getElementById('fApplicant'),
  expense_type: document.getElementById('fExpenseType'),
  merchant:     document.getElementById('fMerchant'),
  total_amount: document.getElementById('fAmount'),
  head_count:   document.getElementById('fHeadCount'),
};

// ── Init ─────────────────────────────────────────────────
guardAuth();
initNav();

// ── File Input ───────────────────────────────────────────
fileInput.addEventListener('change', function () {
  if (fileInput.files.length > 0) handleFile(fileInput.files[0]);
});

// ── Drag & Drop ──────────────────────────────────────────
uploadZone.addEventListener('dragover', function (e) { e.preventDefault(); uploadZone.classList.add('drag-over'); });
uploadZone.addEventListener('dragleave', function () { uploadZone.classList.remove('drag-over'); });
uploadZone.addEventListener('drop', function (e) {
  e.preventDefault();
  uploadZone.classList.remove('drag-over');
  var file = e.dataTransfer.files[0];
  if (file) handleFile(file);
});

// ── Handle File ──────────────────────────────────────────
async function handleFile(file) {
  var validTypes = ['image/jpeg', 'image/png', 'image/jpg'];
  if (!validTypes.includes(file.type)) { showStatus('error', '仅支持 JPG / PNG 格式'); return; }
  if (file.size > 5 * 1024 * 1024) { showStatus('error', '文件大小超过 5MB 限制'); return; }

  var url = URL.createObjectURL(file);
  previewImg.src = url;
  defaultState.style.display = 'none';
  previewRow.classList.add('show');
  uploadZone.classList.add('has-image');
  formCard.style.display = 'block';
  hideStatus(); hideRaw();
  taskUuidDisp.classList.remove('show');
  taskUuidDisp.textContent = '';

  setFormEnabled(false);
  btnSubmit.disabled = true;
  showStatus('info', '⏳ OCR 识别中，请稍候...');

  var formData = new FormData();
  formData.append('file', file);

  try {
    var resp = await fetch('/api/upload', {
      method: 'POST',
      headers: authHeaders(),
      body: formData,
    });
    var json = await resp.json();

    if (resp.ok && json.code === 0) {
      var d = json.data;
      currentTaskUuid = d.uuid;
      fields.applicant.value    = d.applicant || '';
      fields.expense_type.value = d.expense_type || '';
      fields.merchant.value     = d.merchant || '';
      fields.total_amount.value = d.total_amount ?? '';
      fields.head_count.value   = d.head_count ?? 1;

      originalOcrData = {
        applicant:    d.applicant || '',
        expense_type: d.expense_type || '',
        merchant:     d.merchant || '',
        total_amount: d.total_amount ?? '',
        head_count:   d.head_count ?? 1,
      };

      if (d.ocr_raw_text) { rawText.textContent = d.ocr_raw_text; rawToggle.style.display = 'block'; }
      taskUuidDisp.textContent = '任务 ID: ' + d.uuid;
      taskUuidDisp.classList.add('show');

      if (d.total_amount === null || d.total_amount === undefined) {
        showStatus('error', '⚠️ 金额识别失败，请手动输入后提交');
        fields.total_amount.placeholder = '请手动输入金额';
      } else {
        showStatus('success', '✅ OCR 识别完成，请核对并修改，确认后点击提交');
      }
      setFormEnabled(true);
      btnSubmit.disabled = false;
      attachModifyListeners();
    } else {
      currentTaskUuid = json.data && json.data.uuid ? json.data.uuid : null;
      showStatus('error', '❌ 识别失败：' + json.msg);
      setFormEnabled(true);
      if (json.data && json.data.uuid) {
        taskUuidDisp.textContent = '任务 ID: ' + json.data.uuid;
        taskUuidDisp.classList.add('show');
        currentTaskUuid = json.data.uuid;
        btnSubmit.disabled = false;
      }
    }
  } catch (err) {
    showStatus('error', '❌ 网络异常：' + err.message);
    setFormEnabled(true);
  }
}

// ── Modify Listeners ─────────────────────────────────────
function attachModifyListeners() {
  Object.keys(fields).forEach(function (key) {
    fields[key].addEventListener('input', function () {
      var orig = String(originalOcrData[key] || '');
      if (orig !== fields[key].value) fields[key].classList.add('modified');
      else fields[key].classList.remove('modified');
    });
  });
}

// ── Submit to DB ─────────────────────────────────────────
async function submitToDB() {
  if (!currentTaskUuid) { showStatus('error', '请先上传图片'); return; }
  var amount = parseFloat(fields.total_amount.value);
  if (isNaN(amount) || amount <= 0) { showStatus('error', '金额识别失败，请手动输入有效的费用总额'); fields.total_amount.focus(); return; }
  if (!fields.applicant.value.trim()) { showStatus('error', '请填写报销人'); fields.applicant.focus(); return; }
  if (!fields.expense_type.value) { showStatus('error', '请选择报销类型'); fields.expense_type.focus(); return; }

  btnSubmit.disabled = true;
  spinnerSubmit.classList.add('show');
  showStatus('info', '⏳ 正在提交到数据库...');

  var body = {
    applicant:    fields.applicant.value.trim(),
    expense_type: fields.expense_type.value,
    merchant:     fields.merchant.value.trim(),
    total_amount: amount,
    head_count:   parseInt(fields.head_count.value) || 1,
  };

  try {
    var resp = await fetch('/api/receipt/' + currentTaskUuid, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(body),
    });
    var json = await resp.json();
    if (resp.ok && json.code === 0) {
      originalOcrData = Object.assign({}, body);
      Object.keys(fields).forEach(function (k) { fields[k].classList.remove('modified'); });
      showStatus('success', '✅ 数据已成功保存到数据库！');
    } else {
      showStatus('error', '❌ 保存失败：' + json.msg);
    }
  } catch (err) {
    showStatus('error', '❌ 网络异常：' + err.message);
  } finally {
    btnSubmit.disabled = false;
    spinnerSubmit.classList.remove('show');
  }
}

// ── Form Helpers ─────────────────────────────────────────
function setFormEnabled(enabled) {
  Object.keys(fields).forEach(function (k) { fields[k].disabled = !enabled; });
}

function toggleRawText() {
  rawText.classList.toggle('show');
  rawToggle.textContent = rawText.classList.contains('show') ? '▾ 收起 OCR 原始文本' : '▸ 查看 OCR 原始文本';
}

function hideRaw() {
  rawText.classList.remove('show');
  rawText.textContent = '';
  rawToggle.style.display = 'none';
  rawToggle.textContent = '▸ 查看 OCR 原始文本';
}

function resetForm() {
  currentTaskUuid = null; originalOcrData = {};
  Object.keys(fields).forEach(function (k) { fields[k].value = ''; fields[k].classList.remove('modified'); });
  fields.head_count.value = '1';
  previewImg.src = ''; previewRow.classList.remove('show'); defaultState.style.display = '';
  uploadZone.classList.remove('has-image'); fileInput.value = '';
  formCard.style.display = 'none'; hideStatus(); hideRaw();
  taskUuidDisp.classList.remove('show'); taskUuidDisp.textContent = '';
  btnSubmit.disabled = true; setFormEnabled(false);
}
