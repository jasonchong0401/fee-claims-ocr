/**
 * Login Page — handles authentication.
 */
async function doLogin() {
  const username = document.getElementById('username').value.trim();
  const password = document.getElementById('password').value.trim();

  if (!username || !password) {
    showLoginError('请填写用户名和密码');
    return;
  }

  setLoginLoading(true);
  hideLoginError();

  try {
    const resp = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: username, password: password }),
    });
    const json = await resp.json();

    if (resp.ok && json.code === 0) {
      localStorage.setItem('token', json.data.access_token);
      localStorage.setItem('username', json.data.username);
      localStorage.setItem('employee_id', json.data.employee_id || '');
      localStorage.setItem('role', json.data.role);
      window.location.href = '/upload';
    } else {
      showLoginError(json.msg || json.detail || '登录失败');
    }
  } catch (err) {
    showLoginError('网络异常: ' + err.message);
  } finally {
    setLoginLoading(false);
  }
}

function setLoginLoading(loading) {
  document.getElementById('btnLogin').disabled = loading;
  document.getElementById('spinner').classList.toggle('show', loading);
}

function showLoginError(msg) {
  const el = document.getElementById('errorMsg');
  el.textContent = msg;
  el.classList.add('show');
}

function hideLoginError() {
  document.getElementById('errorMsg').classList.remove('show');
}

// Enter key to submit
document.addEventListener('keydown', function (e) {
  if (e.key === 'Enter') doLogin();
});
