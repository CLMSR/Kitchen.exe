/* Shared recipe primitives used by search, feeds and the saved library. */
(() => {
  'use strict';
  const normalizeIngredient = (value) => String(value || '')
    .normalize('NFKD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase().replace(/[^a-z0-9\s-]/g, ' ')
    .replace(/\b(fresh(?:ly)?|chopped|diced|minced|sliced|organic|optional|large|small|medium)\b/g, ' ')
    .replace(/\s+/g, ' ').trim();
  const canonicalUrl = (value) => {
    try {
      const url = new URL(String(value || ''));
      if (!['http:', 'https:'].includes(url.protocol)) return '';
      url.hash = '';
      ['utm_source','utm_medium','utm_campaign','utm_term','utm_content','fbclid','gclid','igshid'].forEach(k => url.searchParams.delete(k));
      url.hostname = url.hostname.toLowerCase();
      if (url.pathname.length > 1) url.pathname = url.pathname.replace(/\/+$/, '');
      return url.href;
    } catch { return ''; }
  };
  const ingredientMatches = (haystack, ingredient) => {
    const h = ` ${normalizeIngredient(haystack)} `;
    const i = normalizeIngredient(ingredient);
    if (!i) return false;
    return h.includes(` ${i} `) || h.includes(` ${i}-`) || h.includes(`-${i} `);
  };
  const durationToMinutes = (value) => {
    const raw = String(value || '').trim();
    if (!raw) return 0;
    const iso = raw.match(/^PT(?:(\d+)H)?(?:(\d+)M)?$/i);
    if (iso) return (Number(iso[1] || 0) * 60) + Number(iso[2] || 0);
    let total = 0, matched = false;
    const h = raw.match(/(\d+)\s*h/i), m = raw.match(/(\d+)\s*m(?:in(?:ute)?s?)?/i);
    if (h) { total += Number(h[1]) * 60; matched = true; }
    if (m) { total += Number(m[1]); matched = true; }
    if (!matched && /^\d+$/.test(raw)) return Number(raw);
    return matched ? total : 0;
  };
  const safeDateIso = (value) => {
    if (!value) return '';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '' : date.toISOString();
  };
  const normalizeRecipe = (input = {}) => {
    const url = canonicalUrl(input.url || input.link || '');
    const ingredients = Array.isArray(input.ingredients) ? input.ingredients : (Array.isArray(input.allIngredients) ? input.allIngredients : []);
    return {
      id: String(input.id || url || `${normalizeIngredient(input.title)}-${input.source || 'unknown'}`),
      title: String(input.title || 'Untitled recipe').trim(),
      url,
      image: canonicalUrl(input.image || '') || '',
      source: String(input.source || 'unknown'),
      sourceLabel: String(input.sourceLabel || input.source || 'Unknown source'),
      excerpt: String(input.excerpt || input.description || '').trim(),
      ingredients: ingredients.map(item => typeof item === 'string' ? { name: item.trim(), normalized: normalizeIngredient(item) } : ({ ...item, name: String(item.name || item.display || '').trim(), normalized: normalizeIngredient(item.name || item.display || '') })).filter(item => item.name),
      instructions: Array.isArray(input.instructions) ? input.instructions : (Array.isArray(input.recipe?.instructions) ? input.recipe.instructions : []),
      date: safeDateIso(input.date || ''),
      raw: input
    };
  };
  window.KitchenRecipeCore = Object.freeze({ normalizeIngredient, canonicalUrl, ingredientMatches, safeDateIso, normalizeRecipe, durationToMinutes });
})();
