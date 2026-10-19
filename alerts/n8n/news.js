// ===== RÉGLAGES =====
const FEEDS = [
  'https://news.google.com/rss/search?q=%EC%A7%80%EA%B5%AC%EC%98%A4%EB%9D%BD%EC%8B%A4+OR+%EC%95%88%EC%9C%A0%EC%A7%84+when:2d&hl=ko&gl=KR&ceid=KR:ko',
  'https://news.google.com/rss/search?q=%22Earth+Arcade%22+OR+%22An+Yujin%22+OR+%22Ahn+Yujin%22+when:2d&hl=en-US&gl=US&ceid=US:en',
  'https://news.google.com/rss/search?q=%22Earth+Arcade%22+OR+%22An+Yujin%22+OR+%22Ahn+Yujin%22+OR+%22Yujin+IVE%22+when:2d&hl=fr&gl=FR&ceid=FR:fr',
];
const EVENT_WORDS = ['콘서트', '팬미팅', '컴백', '쇼케이스', '투어', '예정', '라이브', 'concert', 'fan meeting', 'comeback',
  'tour', 'showcase', 'live', 'season', 'saison', 'tournée'];
const EVERY_MINUTES = 30;
const MAX_PER_MESSAGE = 8;
// ====================

const helpers = this.helpers;
if (!helpers || !helpers.httpRequest) throw new Error('this.helpers.httpRequest indisponible dans ce Code node');

const data = $getWorkflowStaticData('global');
if (Date.now() - (data.lastNews || 0) < (EVERY_MINUTES - 2) * 60 * 1000) return [];
data.lastNews = Date.now();
data.news = data.news || [];
const firstRun = !data.newsInitialized;

const decode = s => String(s || '')
  .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1')
  .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&');
const tag = (xml, name) => {
  const m = xml.match(new RegExp(`<${name}[^>]*>([\\s\\S]*?)</${name}>`));
  return m ? decode(m[1]) : '';
};
const esc = s => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
// Google News ajoute " - Nom du média" : on l'enlève pour repérer le même article dans plusieurs flux
const key = title => title.replace(/\s+-\s+[^-]+$/, '').toLowerCase().replace(/[\s\p{P}\p{S}]+/gu, '');

const HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
  // évite la page de consentement Google sur les serveurs européens
  'Cookie': 'CONSENT=YES+cb; SOCS=CAI',
};
const fresh = [];
const errors = [];
let total = 0;
for (const url of FEEDS) {
  let xml;
  try {
    xml = String(await helpers.httpRequest({ url, headers: HEADERS, json: false }));
  } catch (e) {
    errors.push(e.message);
    continue;
  }
  const items = xml.split('<item>').slice(1);
  if (!items.length) errors.push('réponse sans article : ' + xml.slice(0, 80).replace(/\s+/g, ' '));
  total += items.length;
  for (const it of items) {
    const title = tag(it, 'title');
    const link = tag(it, 'link');
    const k = key(title);
    if (!title || data.news.includes(k) || data.news.includes(link)) continue;
    data.news.push(k, link);
    fresh.push({ title, link, pub: Date.parse(tag(it, 'pubDate')) || 0 });
  }
}
data.news = data.news.slice(-3000);
data.newsInitialized = true;

if (!total) {
  return [{ json: { text: '⚠️ Google News inaccessible depuis n8n :\n' + esc(errors.join('\n').slice(0, 500)) } }];
}
if (!fresh.length) return [];

// au premier lancement, on envoie seulement les 5 plus récentes pour montrer que ça marche
fresh.sort((a, b) => b.pub - a.pub);
const header = firstRun ? '📰 <b>Dernières actus Earth Arcade / Yujin</b>' : '📰 <b>Actus Earth Arcade / Yujin</b>';
const lines = fresh.slice(0, firstRun ? 5 : MAX_PER_MESSAGE).map(n => {
  const prefix = EVENT_WORDS.some(w => n.title.toLowerCase().includes(w)) ? '📅 ' : '• ';
  return `${prefix}<a href="${esc(n.link)}">${esc(n.title)}</a>`;
});
return [{ json: { text: header + '\n' + lines.join('\n') } }];
