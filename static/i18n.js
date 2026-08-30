/* Shared English/Turkish dictionary and switcher for every page.
 *
 * Three kinds of text need handling and they are handled differently:
 *
 *   1. Static markup  — tagged with data-i18n / -ph / -title / -aria and
 *                       rewritten in place by applyI18n().
 *   2. Script-built   — read through t('key') while rendering.
 *   3. Scraped data   — translated server-side; the page just re-fetches with
 *                       ?lang= and the API returns the same field names.
 *
 * The chosen language lives in localStorage under 'lang', the way the existing
 * theme toggle stores 'theme', so it carries across pages without a router or
 * a server session.
 */
const I18N = {
  en: {
    /* chrome */
    'site.title': 'Tem&Tek Technology Tracker Agent',
    'title.news': 'Tem&Tek Technology Tracker Agent',
    'title.beyond': 'Beyond Our Focus — Tem&Tek Technology Tracker Agent',
    'title.companies': 'Company News — Appliance Tracker',
    'title.products': 'Appliance Tech Comparison',
    'title.eprel': 'EPREL Database — Appliance Energy Benchmark',
    'nav.news': 'Tech News',
    'nav.companies': 'Company News',
    'nav.products': 'Products',
    'theme.light': 'Light',
    'theme.dark': 'Dark',
    'lang.name': 'EN',
    'lang.switch': 'Türkçe\'ye geç',
    'common.backToTop': 'Back to top',
    'common.toggleTheme': 'Toggle dark mode',
    'common.all': 'All',
    'common.new': 'New',
    'common.today': 'Today',
    'common.yesterday': 'Yesterday',
    'common.daysAgo': 'd ago',
    'common.showDetails': 'Show details ▸',
    'common.hideDetails': 'Hide details ▾',
    'common.originalTitle': 'Original Title:',
    'common.loading': 'Loading…',
    'common.none': 'No articles found.',

    /* toolbar */
    'filter.allSources': 'All sources',
    'filter.anyTime': 'Any time',
    'filter.past24': 'Past 24 hours',
    'filter.pastWeek': 'Past week',
    'filter.pastMonth': 'Past month',
    'sort.newest': 'Newest first',
    'sort.oldest': 'Oldest first',
    'sort.scoreHigh': 'Relevance ↓',
    'sort.scoreLow': 'Relevance ↑',

    /* tech news */
    'news.search': "Search news... (press '/' to focus)",
    'news.loading': 'Loading news...',
    'news.empty': 'No news yet. The scraper might not have run.',
    'news.beyondLink': 'Beyond Our Focus →',
    'news.beyondHint': 'Wider tech & world news outside our core topics',

    /* beyond */
    'beyond.title': 'Beyond Our Focus',
    'beyond.search': "Search wider news... (press '/' to focus)",
    'beyond.allTopics': 'All topics',
    'beyond.back': '← Back to Tech News',

    /* company news */
    'co.title': 'Company News',
    'co.sub': 'Press releases from top home-appliance companies.',
    'co.search': 'Search releases…',
    'co.allThemes': 'All themes',
    'co.loading': 'Loading company data…',
    'co.empty': 'No releases match your filters.',
    'co.noData': 'No company data yet. Run the company pipeline.',
    'co.releases': 'releases',
    'co.release': 'release',

    /* products */
    'pr.title': 'Appliance Tech Comparison',
    'pr.loading': 'Loading products…',
    'pr.search': 'Search models or brands…',
    'pr.comparison': 'Product comparison',
    'pr.flagships': 'Flagship products',
    'pr.matrix': 'Technology matrix',
    'pr.brand': 'Brand',
    'pr.model': 'Model',
    'pr.product': 'Product',
    'pr.onMarket': 'On Market',
    'pr.eprelLink': 'EPREL Database →',
    'pr.eprelHint': 'EU energy-label registry for every brand',
    'pr.hideUnresearched': 'Hide rows awaiting research',
    'pr.hasAny': 'Has any technology',
    'pr.awaiting': 'Awaiting research',
    'pr.toResearch': 'To research',
    'pr.available': 'Available',
    'pr.partial': 'Partial / select models',
    'pr.notOn': 'Not on flagship',
    'pr.coverage': 'Full availability',
    'pr.view': 'View product ↗',
    'pr.sources': 'ⓘ Sources',
    'pr.sourcesHint': 'Where each ✓ and – comes from',
    'pr.empty': 'No products match.',
    'pr.heatpump': 'Heat-pump',
    'pr.condenser': 'Condenser / vented',
    'pr.noRefs': 'No source pages recorded for this category yet — run',
    'pr.checked': 'checked',
    'pr.matched': 'matched',
    'pr.absent': 'Not mentioned on the page, so recorded as “no”:',

    /* eprel */
    'ep.title': 'EPREL Database',
    'ep.heading': 'EPREL energy database',
    'ep.sub': 'EU energy-label registry, ranked by energy class then energy use.',
    'ep.loading': 'Loading EPREL database…',
    'ep.search': 'Search models or brands…',
    'ep.allBrands': 'All brands',
    'ep.allClasses': 'All energy classes',
    'ep.tracked': 'Tracked brands only',
    'ep.bestPerBrand': 'Best per brand',
    'ep.excel': '⤓ Excel',
    'ep.excelHint': 'Download the filtered table as an Excel workbook (.xlsx)',
    'ep.showMore': 'Show more',
    'ep.back': '← Back to Products',
    'ep.empty': 'No models match these filters.',
    'ep.bestClass': 'Best class',
    'ep.allShown': 'All shown',
    'ep.flagHint': 'EPREL registration declares values that contradict each other',

    /* machine types — shared by both product pages */
    'cat.washing-machine': 'Washing Machines',
    'cat.washer-dryer': 'Washer-Dryers',
    'cat.dryer': 'Dryers',
    'cat.dishwasher': 'Dishwashers',

    /* the six fixed classes, long and short forms */
    'cls.Sustainability & Environmental Impact': 'Sustainability & Environmental Impact',
    'cls.Fabric Care & Textile Engineering': 'Fabric Care & Textile Engineering',
    'cls.Chemical Interaction & Smart Dosing': 'Chemical Interaction & Smart Dosing',
    'cls.Hygiene & Health Technologies': 'Hygiene & Health Technologies',
    'cls.AI, IoT & Smart Sensors': 'AI, IoT & Smart Sensors',
    'cls.Other': 'Other',
    'short.Sustainability & Environmental Impact': 'Sustainability',
    'short.Fabric Care & Textile Engineering': 'Fabric Care',
    'short.Chemical Interaction & Smart Dosing': 'Smart Dosing',
    'short.Hygiene & Health Technologies': 'Hygiene',
    'short.AI, IoT & Smart Sensors': 'AI & IoT',
    'short.Other': 'Other',

    /* company themes (keyword-tagged, fixed set) */
    'th.Laundry': 'Laundry',
    'th.Design & Events': 'Design & Events',
    'th.Business & Corporate': 'Business & Corporate',
    'th.AI': 'AI',
    'th.IoT & Connectivity': 'IoT & Connectivity',
    'th.Cooking & Kitchen': 'Cooking & Kitchen',
    'th.Sustainability & Energy': 'Sustainability & Energy',
    'th.Refrigeration': 'Refrigeration',
    'th.Hygiene & Health': 'Hygiene & Health',
    'th.Other': 'Other'
  },

  tr: {
    /* chrome */
    'site.title': 'Tem&Tek Teknoloji Takip Ajanı',
    'title.news': 'Tem&Tek Teknoloji Takip Ajanı',
    'title.beyond': 'Odağımızın Dışında — Tem&Tek Teknoloji Takip Ajanı',
    'title.companies': 'Şirket Haberleri — Beyaz Eşya Takipçisi',
    'title.products': 'Beyaz Eşya Teknoloji Karşılaştırması',
    'title.eprel': 'EPREL Veritabanı — Beyaz Eşya Enerji Karşılaştırması',
    'nav.news': 'Teknoloji Haberleri',
    'nav.companies': 'Şirket Haberleri',
    'nav.products': 'Ürünler',
    'theme.light': 'Açık',
    'theme.dark': 'Koyu',
    'lang.name': 'TR',
    'lang.switch': 'Switch to English',
    'common.backToTop': 'Başa dön',
    'common.toggleTheme': 'Koyu temayı aç/kapat',
    'common.all': 'Tümü',
    'common.new': 'Yeni',
    'common.today': 'Bugün',
    'common.yesterday': 'Dün',
    'common.daysAgo': ' gün önce',
    'common.showDetails': 'Ayrıntıları göster ▸',
    'common.hideDetails': 'Ayrıntıları gizle ▾',
    'common.originalTitle': 'Orijinal Başlık:',
    'common.loading': 'Yükleniyor…',
    'common.none': 'Sonuç bulunamadı.',

    /* toolbar */
    'filter.allSources': 'Tüm kaynaklar',
    'filter.anyTime': 'Tüm zamanlar',
    'filter.past24': 'Son 24 saat',
    'filter.pastWeek': 'Son hafta',
    'filter.pastMonth': 'Son ay',
    'sort.newest': 'Önce en yeni',
    'sort.oldest': 'Önce en eski',
    'sort.scoreHigh': 'İlgi düzeyi ↓',
    'sort.scoreLow': 'İlgi düzeyi ↑',

    /* tech news */
    'news.search': "Haberlerde ara... ('/' ile odaklan)",
    'news.loading': 'Haberler yükleniyor...',
    'news.empty': 'Henüz haber yok. Tarayıcı çalışmamış olabilir.',
    'news.beyondLink': 'Odağımızın Dışında →',
    'news.beyondHint': 'Ana konularımızın dışındaki teknoloji ve dünya haberleri',

    /* beyond */
    'beyond.title': 'Odağımızın Dışında',
    'beyond.search': "Diğer haberlerde ara... ('/' ile odaklan)",
    'beyond.allTopics': 'Tüm konular',
    'beyond.back': '← Teknoloji Haberlerine dön',

    /* company news */
    'co.title': 'Şirket Haberleri',
    'co.sub': 'Önde gelen beyaz eşya şirketlerinden basın bültenleri.',
    'co.search': 'Bültenlerde ara…',
    'co.allThemes': 'Tüm temalar',
    'co.loading': 'Şirket verileri yükleniyor…',
    'co.empty': 'Filtrelerinize uyan bülten yok.',
    'co.noData': 'Henüz şirket verisi yok. Şirket hattını çalıştırın.',
    'co.releases': 'bülten',
    'co.release': 'bülten',

    /* products */
    'pr.title': 'Beyaz Eşya Teknoloji Karşılaştırması',
    'pr.loading': 'Ürünler yükleniyor…',
    'pr.search': 'Model veya marka ara…',
    'pr.comparison': 'Ürün karşılaştırması',
    'pr.flagships': 'Amiral gemisi ürünler',
    'pr.matrix': 'Teknoloji matrisi',
    'pr.brand': 'Marka',
    'pr.model': 'Model',
    'pr.product': 'Ürün',
    'pr.onMarket': 'Piyasada',
    'pr.eprelLink': 'EPREL Veritabanı →',
    'pr.eprelHint': 'Tüm markalar için AB enerji etiketi kaydı',
    'pr.hideUnresearched': 'Araştırma bekleyen satırları gizle',
    'pr.hasAny': 'Herhangi bir teknolojisi olanlar',
    'pr.awaiting': 'Araştırma bekliyor',
    'pr.toResearch': 'Araştırılacak',
    'pr.available': 'Mevcut',
    'pr.partial': 'Kısmi / belirli modeller',
    'pr.notOn': 'Bu modelde yok',
    'pr.coverage': 'Tam kapsam',
    'pr.view': 'Ürünü görüntüle ↗',
    'pr.sources': 'ⓘ Kaynaklar',
    'pr.sourcesHint': 'Her ✓ ve – işaretinin dayanağı',
    'pr.empty': 'Eşleşen ürün yok.',
    'pr.heatpump': 'Isı pompalı',
    'pr.condenser': 'Kondenserli / bacalı',
    'pr.noRefs': 'Bu kategori için henüz kaynak sayfa kaydedilmedi — çalıştırın:',
    'pr.checked': 'kontrol edildi',
    'pr.matched': 'eşleşen ifade',
    'pr.absent': 'Sayfada geçmediği için “yok” olarak kaydedildi:',

    /* eprel */
    'ep.title': 'EPREL Veritabanı',
    'ep.heading': 'EPREL enerji veritabanı',
    'ep.sub': 'AB enerji etiketi kaydı; enerji sınıfına, ardından enerji tüketimine göre sıralanmıştır.',
    'ep.loading': 'EPREL veritabanı yükleniyor…',
    'ep.search': 'Model veya marka ara…',
    'ep.allBrands': 'Tüm markalar',
    'ep.allClasses': 'Tüm enerji sınıfları',
    'ep.tracked': 'Sadece takip edilen markalar',
    'ep.bestPerBrand': 'Marka başına en iyi',
    'ep.excel': '⤓ Excel',
    'ep.excelHint': 'Filtrelenmiş tabloyu Excel dosyası (.xlsx) olarak indir',
    'ep.showMore': 'Daha fazla göster',
    'ep.back': '← Ürünlere dön',
    'ep.empty': 'Bu filtrelere uyan model yok.',
    'ep.bestClass': 'En iyi sınıf',
    'ep.allShown': 'Tümü gösteriliyor',
    'ep.flagHint': 'EPREL kaydı birbiriyle çelişen değerler bildiriyor',

    /* machine types */
    'cat.washing-machine': 'Çamaşır Makineleri',
    'cat.washer-dryer': 'Kurutmalı Çamaşır Makineleri',
    'cat.dryer': 'Kurutma Makineleri',
    'cat.dishwasher': 'Bulaşık Makineleri',

    /* the six fixed classes */
    'cls.Sustainability & Environmental Impact': 'Sürdürülebilirlik ve Çevresel Etki',
    'cls.Fabric Care & Textile Engineering': 'Kumaş Bakımı ve Tekstil Mühendisliği',
    'cls.Chemical Interaction & Smart Dosing': 'Kimyasal Etkileşim ve Akıllı Dozajlama',
    'cls.Hygiene & Health Technologies': 'Hijyen ve Sağlık Teknolojileri',
    'cls.AI, IoT & Smart Sensors': 'Yapay Zekâ, IoT ve Akıllı Sensörler',
    'cls.Other': 'Diğer',
    'short.Sustainability & Environmental Impact': 'Sürdürülebilirlik',
    'short.Fabric Care & Textile Engineering': 'Kumaş Bakımı',
    'short.Chemical Interaction & Smart Dosing': 'Akıllı Dozajlama',
    'short.Hygiene & Health Technologies': 'Hijyen',
    'short.AI, IoT & Smart Sensors': 'YZ ve IoT',
    'short.Other': 'Diğer',

    /* company themes */
    'th.Laundry': 'Çamaşır',
    'th.Design & Events': 'Tasarım ve Etkinlikler',
    'th.Business & Corporate': 'İş ve Kurumsal',
    'th.AI': 'Yapay Zekâ',
    'th.IoT & Connectivity': 'IoT ve Bağlantı',
    'th.Cooking & Kitchen': 'Pişirme ve Mutfak',
    'th.Sustainability & Energy': 'Sürdürülebilirlik ve Enerji',
    'th.Refrigeration': 'Soğutma',
    'th.Hygiene & Health': 'Hijyen ve Sağlık',
    'th.Other': 'Diğer'
  }
};

let LANG = 'en';
try {
  const saved = localStorage.getItem('lang');
  if (saved === 'tr' || saved === 'en') LANG = saved;
} catch (e) { /* private mode: fall back to English */ }

/* Look up a key. Falls back to English, then to the supplied default, then to
   the key itself — a missing translation shows English, never blank. */
function t(key, fallback) {
  const table = I18N[LANG] || I18N.en;
  if (table[key] !== undefined) return table[key];
  if (I18N.en[key] !== undefined) return I18N.en[key];
  return fallback !== undefined ? fallback : key;
}

/* Config-driven labels (product categories, spec columns, technologies) carry
   their own Turkish alongside the English, because they are data the configs
   own rather than UI strings this file could enumerate. L() picks the right
   one and falls back to English when a translation has not been filled in. */
function L(obj, field) {
  if (!obj) return '';
  const key = field || 'label';
  if (LANG === 'tr' && obj[key + '_tr']) return obj[key + '_tr'];
  return obj[key] || '';
}

/* Classification and theme labels arrive as English strings inside the data,
   so they are translated by value rather than by a key the caller invents. */
function tClass(name) { return t('cls.' + name, name); }
function tShort(name) { return t('short.' + name, name); }
function tTheme(name) { return t('th.' + name, name); }
function tCat(key, fallback) { return t('cat.' + key, fallback); }

/* Rewrite everything tagged in the markup. Safe to call repeatedly. */
function applyI18n(root) {
  const scope = root || document;
  scope.querySelectorAll('[data-i18n]').forEach(el => {
    el.textContent = t(el.getAttribute('data-i18n'));
  });
  scope.querySelectorAll('[data-i18n-ph]').forEach(el => {
    el.placeholder = t(el.getAttribute('data-i18n-ph'));
  });
  scope.querySelectorAll('[data-i18n-title]').forEach(el => {
    el.title = t(el.getAttribute('data-i18n-title'));
  });
  scope.querySelectorAll('[data-i18n-aria]').forEach(el => {
    el.setAttribute('aria-label', t(el.getAttribute('data-i18n-aria')));
  });
  const meta = document.querySelector('meta[name="i18n-title"]');
  if (meta && meta.content) document.title = t(meta.content);
  document.documentElement.lang = LANG;
}

/* Wire the header button. `onChange` re-renders the page — data endpoints are
   re-fetched with the new ?lang= there, because scraped text is translated
   server-side. */
function initLang(onChange) {
  applyI18n();
  const btn = document.getElementById('langToggle');
  if (!btn) return;
  const paint = () => { btn.textContent = LANG === 'tr' ? 'EN' : 'TR'; btn.title = t('lang.switch'); };
  paint();
  btn.addEventListener('click', () => {
    LANG = LANG === 'tr' ? 'en' : 'tr';
    try { localStorage.setItem('lang', LANG); } catch (e) { /* ignore */ }
    applyI18n();
    paint();
    if (typeof onChange === 'function') onChange(LANG);
  });
}

/* Suffix for the data endpoints. */
function langQuery(sep) { return (sep || '?') + 'lang=' + LANG; }

/* Translate the static markup as soon as the DOM exists, without waiting for a
   page's init() to reach initLang(). Otherwise the loading message and toolbar
   would flash English on a Turkish session while the data request is in
   flight. Pages still call initLang() to wire the button and their re-render. */
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => applyI18n());
} else {
  applyI18n();
}
