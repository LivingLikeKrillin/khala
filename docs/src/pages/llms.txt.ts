import type { APIRoute } from 'astro';
import { getCollection } from 'astro:content';

// Served at /khala/llms.txt — a curated index of the English docs for LLMs,
// following the llms.txt convention. Generated at build time (no plugin).
const SITE = 'https://livinglikekrillin.github.io/khala';

// A sensible reading order; anything not listed sorts after, alphabetically.
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

export const GET: APIRoute = async () => {
  const docs = (await getCollection('docs', (e) => !e.id.startsWith('ko/'))).sort(
    (a, b) => rank(a.id) - rank(b.id) || a.id.localeCompare(b.id),
  );

  const lines: string[] = [
    '# Khala',
    '',
    '> Grounded answers about your code, docs, and services, every one backed by a source. An alliance of tools (Nexus, Archon, Observer, Arbiter, Probe) that connect only through Khala, the shared link.',
    '',
    '## Docs',
    '',
  ];
  for (const e of docs) {
    const url = e.id === 'index' ? `${SITE}/` : `${SITE}/${e.id}/`;
    const desc = e.data.description ? `: ${e.data.description}` : '';
    lines.push(`- [${e.data.title}](${url})${desc}`);
  }
  lines.push('');
  lines.push('The full text of every page is available at ' + SITE + '/llms-full.txt.');
  lines.push('');

  return new Response(lines.join('\n'), {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
};
