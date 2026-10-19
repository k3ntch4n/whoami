// ===== RÉGLAGES =====
// Chaînes surveillées : @handle ou ID "UC..." (Partager la chaîne > Copier l'ID de la chaîne)
const CHANNELS = ['@tvN', '@IVEstarship', '@channel15ya'];
const KEYWORDS = ['지구오락실', '지락실', 'earth arcade', '안유진', 'an yujin', 'ahn yujin', 'yujin'];
// ====================

const helpers = this.helpers;
if (!helpers || !helpers.httpRequest) throw new Error('this.helpers.httpRequest indisponible dans ce Code node');

const data = $getWorkflowStaticData('global');
data.seen = data.seen || [];
data.pending = data.pending || {};
data.ids = data.ids || {};
data.warned = data.warned || [];
const firstRun = !data.initialized;
const out = [];

// le cookie évite la page de consentement YouTube sur les serveurs européens
const HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
  'Accept-Language': 'fr-FR,fr;q=0.9',
  'Cookie': 'CONSENT=YES+cb; SOCS=CAI',
};
const get = async url => String(await helpers.httpRequest({ url, headers: HEADERS, json: false }));
const decode = s => String(s || '')
  .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1')
  .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&');
const tag = (xml, name) => {
  const m = xml.match(new RegExp(`<${name}[^>]*>([\\s\\S]*?)</${name}>`));
  return m ? decode(m[1]) : '';
};
const esc = s => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const fmt = ts => new Date(ts * 1000).toLocaleString('fr-FR', {
  timeZone: 'Europe/Paris', weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
});

async function channelId(c) {
  if (c.startsWith('UC')) return c;
  if (data.ids[c]) return data.ids[c];
  const html = await get('https://www.youtube.com/' + c);
  const m = html.match(/"externalId":"(UC[\w-]{22})"/) || html.match(/youtube\.com\/channel\/(UC[\w-]{22})/);
  if (!m) throw new Error('ID introuvable');
  data.ids[c] = m[1];
  return m[1];
}

async function getStatus(videoId) {
  try {
    const html = await get('https://www.youtube.com/watch?v=' + videoId);
    if (html.includes('"isLiveNow":true')) return { status: 'live' };
    if (html.includes('"isUpcoming":true')) {
      const m = html.match(/"(?:scheduledStartTime|startTime)":"(\d+)"/);
      return { status: 'upcoming', start: m ? Number(m[1]) : null };
    }
    return { status: 'none' };
  } catch (e) {
    return { status: 'error' };
  }
}

// 1) Nouvelles vidéos
for (const c of CHANNELS) {
  let entries;
  try {
    const id = await channelId(c);
    entries = (await get('https://www.youtube.com/feeds/videos.xml?channel_id=' + id)).split('<entry>').slice(1);
  } catch (e) {
    if (!data.warned.includes(c)) {
      data.warned.push(c);
      out.push({ json: { text: `⚠️ Chaîne YouTube introuvable : ${esc(c)}\nRemplace-la par son ID « UC… » dans le nœud « Videos et lives ».` } });
    }
    continue;
  }
  for (const e of entries.reverse()) {
    const vid = tag(e, 'yt:videoId');
    if (!vid || data.seen.includes(vid)) continue;
    data.seen.push(vid);

    const title = tag(e, 'title');
    const text = `${title} ${tag(e, 'media:description')}`.toLowerCase();
    if (!KEYWORDS.some(k => text.includes(k))) continue;

    const s = await getStatus(vid);
    if (s.status === 'upcoming') data.pending[vid] = { title, added: Date.now() };
    if (firstRun) continue;

    let head = '🎬 <b>Nouvelle vidéo</b>';
    if (s.status === 'live') head = '🔴 <b>EN DIRECT maintenant !</b>';
    if (s.status === 'upcoming') head = '⏰ <b>Live programmé</b>' + (s.start ? ` — ${fmt(s.start)}` : '');
    out.push({ json: { text: `${head}\n<b>${esc(title)}</b>\nhttps://www.youtube.com/watch?v=${vid}` } });
  }
}

// 2) Lives programmés : notification quand ils démarrent
for (const [vid, p] of Object.entries(data.pending)) {
  if (Date.now() - p.added > 3 * 24 * 3600 * 1000) { delete data.pending[vid]; continue; }
  const s = await getStatus(vid);
  if (s.status === 'live') {
    out.push({ json: { text: `🔴 <b>EN DIRECT maintenant !</b>\n<b>${esc(p.title)}</b>\nhttps://www.youtube.com/watch?v=${vid}` } });
    delete data.pending[vid];
  } else if (s.status === 'none') {
    delete data.pending[vid]; // terminé ou annulé
  }
}

if (firstRun) {
  out.push({ json: { text: '✅ Alertes YouTube activées : vidéos et lives Earth Arcade / An Yujin.' } });
}
data.seen = data.seen.slice(-2000);
data.initialized = true;
return out;
