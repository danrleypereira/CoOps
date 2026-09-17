import { describe, test, expect } from 'vitest';
import { escapeHtml } from './sanitize';

describe('escapeHtml', () => {
  test('returns plain strings unchanged', () => {
    expect(escapeHtml('hello world')).toBe('hello world');
    expect(escapeHtml('')).toBe('');
  });

  test('escapes each special character', () => {
    expect(escapeHtml('&')).toBe('&amp;');
    expect(escapeHtml('<')).toBe('&lt;');
    expect(escapeHtml('>')).toBe('&gt;');
    expect(escapeHtml('"')).toBe('&quot;');
    expect(escapeHtml("'")).toBe('&#39;');
  });

  test('escapes all occurrences, and ampersand first (no double escaping)', () => {
    expect(escapeHtml('<script>alert("x" & \'y\')</script>')).toBe(
      '&lt;script&gt;alert(&quot;x&quot; &amp; &#39;y&#39;)&lt;/script&gt;'
    );
    expect(escapeHtml('&lt;')).toBe('&amp;lt;');
  });

  test('escaped output renders as literal text in innerHTML', () => {
    const div = document.createElement('div');
    const payload = '<img src=x onerror="alert(1)">';
    div.innerHTML = escapeHtml(payload);
    expect(div.querySelector('img')).toBeNull();
    expect(div.textContent).toBe(payload);
  });
});
