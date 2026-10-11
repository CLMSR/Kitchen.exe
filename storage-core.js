/* Kitchen.exe storage adapter: defensive reads/writes and backward-compatible keys. */
(() => {
  'use strict';
  const prefix = 'kitchenExe';
  function read(key, fallback) {
    try {
      const raw = window.localStorage.getItem(key);
      if (raw == null) return fallback;
      return key === `${prefix}Theme` || key === `${prefix}AutoRefresh` ? raw : JSON.parse(raw);
    } catch (error) {
      console.warn('[KitchenStorage] Could not read stored value:', key, error);
      return fallback;
    }
  }
  function write(key, value) {
    try {
      const serialized = typeof value === 'string' ? value : JSON.stringify(value);
      window.localStorage.setItem(key, serialized);
      return true;
    } catch (error) {
      console.warn('[KitchenStorage] Could not persist value:', key, error);
      return false;
    }
  }
  window.KitchenStorage = Object.freeze({ read, write });
})();
