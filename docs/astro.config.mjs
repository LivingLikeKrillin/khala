// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import { visit } from 'unist-util-visit';

// Browser-free `pre-mermaid` strategy: rewrite ```mermaid fenced code blocks
// into `<pre class="mermaid">…</pre>` so a page-scoped, locally-bundled mermaid
// script (imported from node_modules inside ecosystem.mdx) renders them in the
// browser. Mermaid is bundled at build time (same origin, versioned by
// package-lock) — no unpinned third-party CDN / SRI exposure.
//
// NOTE: rehype-mermaid's own `pre-mermaid` strategy is NOT used because its
// module statically imports `mermaid-isomorphic`, which imports Playwright at
// load time — that would require Chromium at build and break Cloudflare Pages.
// This local plugin produces identical output without any browser dependency.
function rehypeMermaidPre() {
  /** @param {import('hast').Root} tree */
  return (tree) => {
    visit(tree, 'element', (node) => {
      if (node.tagName !== 'pre') return;
      const code = node.children?.[0];
      if (!code || code.type !== 'element' || code.tagName !== 'code') return;
      const className = code.properties?.className;
      const classes = Array.isArray(className) ? className : className ? [className] : [];
      if (!classes.includes('language-mermaid')) return;
      const value = (code.children ?? [])
        .map(/** @param {import('hast').ElementContent} child */ (child) =>
          child.type === 'text' ? child.value : '')
        .join('');
      node.properties = { className: ['mermaid'] };
      node.children = [{ type: 'text', value }];
    });
  };
}

export default defineConfig({
  site: 'https://khala-docs.pages.dev',
  markdown: {
    rehypePlugins: [rehypeMermaidPre],
  },
  integrations: [
    starlight({
      title: 'Khala',
      tagline: 'AI 시대의 캘리브레이션 — 도구들의 연합',
      customCss: ['./src/styles/theme.css'],
      components: {
        Head: './src/components/Head.astro',
      },
      logo: { src: './src/assets/logo.svg', alt: 'Khala' },
      defaultLocale: 'root',
      locales: {
        root: { label: 'English', lang: 'en' },
        ko: { label: '한국어', lang: 'ko' },
      },
      social: {
        github: 'https://github.com/LivingLikeKrillin',
      },
      sidebar: [
        {
          label: 'Overview',
          translations: { ko: '개요' },
          items: [
            { label: 'What is Khala?', slug: 'index' },
            { label: 'Philosophy', translations: { ko: '철학' }, slug: 'philosophy' },
            { label: 'Getting Started', translations: { ko: '시작하기' }, slug: 'start' },
            { label: 'Ecosystem', translations: { ko: '생태계' }, slug: 'ecosystem' },
          ],
        },
        {
          label: 'Tools',
          translations: { ko: '도구' },
          items: [
            { label: 'Nexus', slug: 'tools/nexus' },
            { label: 'Archon', slug: 'tools/archon' },
            { label: 'Probe', slug: 'tools/probe' },
            { label: 'specledger', slug: 'tools/specledger' },
            { label: 'mutqa', slug: 'tools/mutqa' },
          ],
        },
        {
          label: 'Contributing',
          translations: { ko: '기여' },
          items: [{ label: 'Contributing', slug: 'contributing' }],
        },
      ],
    }),
  ],
});
