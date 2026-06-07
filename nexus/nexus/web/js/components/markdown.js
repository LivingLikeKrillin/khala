/**
 * Markdown 렌더링 (marked + DOMPurify).
 */

export function renderMarkdown(text) {
  if (!text) return '';
  const raw = marked.parse(text);
  return DOMPurify.sanitize(raw);
}
