(function () {
  const DEFAULT_API_BASE_URL = 'http://localhost:8000';

  function getApiBaseUrl() {
    const config = window.BUDDY_CONFIG || {};
    return String(config.API_BASE_URL || DEFAULT_API_BASE_URL).replace(/\/+$/, '');
  }

  async function request(path, options = {}) {
    const apiPath = path.startsWith('/') ? path : `/${path}`;
    const headers = {
      Accept: 'application/json',
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {}),
    };

    const response = await fetch(`${getApiBaseUrl()}${apiPath}`, {
      ...options,
      headers,
    });
    const contentType = response.headers.get('content-type') || '';
    const body = contentType.includes('application/json')
      ? await response.json()
      : await response.text();

    if (!response.ok) {
      const message = typeof body === 'string' ? body : JSON.stringify(body);
      throw new Error(message || `HTTP ${response.status}`);
    }

    return body;
  }

  window.BuddyApi = {
    getApiBaseUrl,
    request,
  };
})();
