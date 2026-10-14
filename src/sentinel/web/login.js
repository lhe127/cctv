(() => {
  const form = document.getElementById('login-form');
  const input = document.getElementById('api-key');
  const button = document.getElementById('login-button');
  const error = document.getElementById('login-error');
  const toggle = document.getElementById('toggle-key');

  if (sessionStorage.getItem('sentinel_api_key')) {
    window.location.replace('/dashboard');
    return;
  }

  toggle.addEventListener('click', () => {
    const showing = input.type === 'text';
    input.type = showing ? 'password' : 'text';
    toggle.setAttribute('aria-label', showing ? 'Show API key' : 'Hide API key');
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    error.textContent = '';
    button.disabled = true;
    button.classList.add('is-loading');
    const key = input.value.trim();
    try {
      const response = await fetch('/api/v1/session', {method: 'POST', headers: {'X-API-Key': key}});
      if (!response.ok) throw new Error(response.status === 401 ? 'That API key is not valid.' : 'The server could not verify the key.');
      sessionStorage.setItem('sentinel_api_key', key);
      window.location.replace('/dashboard');
    } catch (reason) {
      error.textContent = reason.message || 'Could not connect to the server.';
      input.focus();
      input.select();
      button.disabled = false;
      button.classList.remove('is-loading');
    }
  });
})();
