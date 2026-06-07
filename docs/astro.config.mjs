// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
  site: 'https://khala-docs.pages.dev',
  integrations: [
    starlight({
      title: 'Khala',
      tagline: 'AI 시대의 캘리브레이션 — 도구들의 연합',
      logo: { src: './src/assets/logo.png', alt: 'Khala' },
      defaultLocale: 'root',
      locales: {
        root: { label: 'English', lang: 'en' },
        ko: { label: '한국어', lang: 'ko' },
      },
      social: [
        { icon: 'github', label: 'GitHub', href: 'https://github.com/LivingLikeKrillin' },
      ],
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
