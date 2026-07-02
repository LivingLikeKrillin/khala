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
// GitHub Pages serves this project site under /khala/. Starlight base-prefixes
// its own nav/sidebar (slug-derived) but NOT author-written links in page
// *bodies* (markdown links/images, MDX <LinkCard href>). This plugin prepends
// the base to root-absolute internal URLs in the content tree so authors keep
// writing base-agnostic `/tools/nexus/` and `/diagrams/x.svg`. (Hero actions
// live in frontmatter, outside this tree — they carry the base explicitly.)
const BASE = '/khala';

function rehypeBaseUrl() {
  /** @param {string} url */
  const withBase = (url) => {
    if (!url.startsWith('/') || url.startsWith('//')) return url; // external / protocol-relative / non-absolute
    if (url === BASE || url.startsWith(BASE + '/')) return url; // already based (e.g. Starlight-emitted)
    return BASE + url;
  };
  /** @param {import('hast').Root} tree */
  return (tree) => {
    // `node` is `any`: the content tree mixes hast elements with MDX JSX nodes
    // (mdxJsxFlowElement/…), which @types/hast does not model.
    visit(tree, (/** @type {any} */ node) => {
      if (node.type === 'element' && node.properties) {
        if (typeof node.properties.href === 'string') node.properties.href = withBase(node.properties.href);
        if (typeof node.properties.src === 'string') node.properties.src = withBase(node.properties.src);
      } else if (node.type === 'mdxJsxFlowElement' || node.type === 'mdxJsxTextElement') {
        for (const attr of node.attributes ?? []) {
          if (attr.type === 'mdxJsxAttribute' && (attr.name === 'href' || attr.name === 'src') && typeof attr.value === 'string') {
            attr.value = withBase(attr.value);
          }
        }
      }
      // NOTE: raw HTML in .md (e.g. <img src="/diagrams/x.svg">) is not reachable
      // here — Astro stringifies it outside the rehype element/JSX tree. Those few
      // <img> tags carry the /khala base explicitly (like the frontmatter hero).
    });
  };
}

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
  // GitHub Pages project site: served under /khala/ (see BASE above).
  site: 'https://livinglikekrillin.github.io',
  base: BASE,
  // Component rename (ADR-0005): old tool slugs redirect to new ones.
  // NOTE: /tools/probe is intentionally NOT redirected — that slug is now a LIVE
  // page (the mutation tool, formerly mutqa, took the "Probe" name). The old
  // review tool moved to /tools/observer. Only freed slugs are redirected.
  redirects: {
    '/tools/specledger': '/tools/arbiter',
    '/tools/mutqa': '/tools/probe',
    '/ko/tools/specledger': '/ko/tools/arbiter',
    '/ko/tools/mutqa': '/ko/tools/probe',
  },
  markdown: {
    rehypePlugins: [rehypeMermaidPre, rehypeBaseUrl],
  },
  integrations: [
    starlight({
      title: 'Khala',
      tagline: '코드·문서·서비스에 대한, 출처가 붙는 답',
      customCss: ['./src/styles/theme.css'],
      components: {
        Head: './src/components/Head.astro',
        PageTitle: './src/components/PageTitle.astro',
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
            { label: 'Nexus — Using the web', translations: { ko: 'Nexus 웹 사용 가이드' }, slug: 'tools/nexus-web' },
            { label: 'Archon', slug: 'tools/archon' },
            { label: 'Observer', slug: 'tools/observer' },
            { label: 'Arbiter', slug: 'tools/arbiter' },
            { label: 'Probe', slug: 'tools/probe' },
            { label: 'Adept', slug: 'tools/adept' },
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
