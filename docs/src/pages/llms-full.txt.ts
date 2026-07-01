import type { APIRoute } from 'astro';

// Served at /khala/llms-full.txt — the full text of the English docs
// concatenated for LLM ingestion. Generated at build time from the raw
// Markdown sources (inline SVG figures and MDX imports stripped as noise).
const rawModules = import.meta.glob('../content/docs/**/*.{md,mdx}', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

const ORDER = [
  'index',
  'start',
  'philosophy',
  'ecosystem',
  'tools/nexus',
  'tools/nexus-web',
  'tools/archon',
  'tools/observer',
  'tools/arbiter',
  'tools/probe',
  'contributing',
];
const rank = (id: string) => {
  const i = ORDER.indexOf(id);
  return i === -1 ? ORDER.length : i;
};

const idFromPath = (p: string) =>
  p.replace(/^.*\/content\/docs\//, '').replace(/\.(md|mdx)$/, '');

const clean = (s: string) =>
  s
    .replace(/^---\n[\s\S]*?\n---\n/, '') // frontmatter
    .replace(/<svg[\s\S]*?<\/svg>/g, '') // inline figures
    .replace(/^import .*$/gm, '') // MDX imports
    .replace(/\n{3,}/g, '\n\n')
    .trim();

export const GET: APIRoute = async () => {
  const entries = Object.entries(rawModules)
    .map(([p, body]) => ({ id: idFromPath(p), body }))
    .filter((e) => !e.id.startsWith('ko/'))
    .sort((a, b) => rank(a.id) - rank(b.id) || a.id.localeCompare(b.id));

  const body = entries.map((e) => clean(e.body)).join('\n\n---\n\n');

  return new Response(`# Khala — full documentation\n\n${body}\n`, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
};
