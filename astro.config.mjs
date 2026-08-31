import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

const repository = 'https://github.com/jfpio/harcerz-w-polu';
const publicSite = 'https://jfpio.github.io/harcerz-w-polu';

export default defineConfig({
  site: 'https://jfpio.github.io',
  base: '/harcerz-w-polu',
  integrations: [
    starlight({
      title: 'Harcerz w polu',
      description: 'Zabawy i gry terenowe Zygmunta Wyrobka — cyfrowa transkrypcja wydania z 1946 roku.',
      favicon: '/book/favicon.png',
      customCss: ['./src/styles/book.css'],
      locales: {
        root: { label: 'Polski', lang: 'pl' },
      },
      social: [{ icon: 'github', label: 'Repozytorium GitHub', href: repository }],
      editLink: { baseUrl: `${repository}/edit/main/` },
      lastUpdated: true,
      pagination: true,
      credits: true,
      head: [
        { tag: 'meta', attrs: { property: 'og:type', content: 'book' } },
        { tag: 'meta', attrs: { property: 'og:site_name', content: 'Harcerz w polu' } },
        { tag: 'meta', attrs: { property: 'og:image', content: `${publicSite}/book/cover.jpg` } },
        { tag: 'meta', attrs: { name: 'twitter:card', content: 'summary_large_image' } },
        { tag: 'meta', attrs: { name: 'twitter:image', content: `${publicSite}/book/cover.jpg` } },
      ],
      sidebar: [
        { label: 'Start', slug: 'index' },
        { label: 'Spis treści', slug: 'spis-tresci' },
        {
          label: 'Wprowadzenie',
          items: [{ autogenerate: { directory: 'wprowadzenie' } }],
        },
        {
          label: 'Orientowanie się w terenie',
          collapsed: false,
          items: [{ autogenerate: { directory: 'gry/orientowanie' } }],
        },
        {
          label: 'Wzrok i spostrzegawczość',
          collapsed: false,
          items: [{ autogenerate: { directory: 'gry/wzrok-spostrzegawczosc' } }],
        },
        {
          label: 'Słuch',
          collapsed: false,
          items: [{ autogenerate: { directory: 'gry/sluch' } }],
        },
        {
          label: 'Zwiady',
          collapsed: false,
          items: [{ autogenerate: { directory: 'gry/zwiady' } }],
        },
        {
          label: 'Ćwiczenia w większym zespole',
          collapsed: false,
          items: [{ autogenerate: { directory: 'gry/wiekszy-zespol' } }],
        },
        { label: 'O wydaniu cyfrowym', slug: 'o-wydaniu' },
      ],
    }),
  ],
});
