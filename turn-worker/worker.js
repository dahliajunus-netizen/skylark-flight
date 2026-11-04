// Hands Skylark players short-lived passwords for Cloudflare's TURN relay, which carries the connection for
// players whose networks block direct links. The TURN key's API token stays here as a secret (TURN_API_TOKEN);
// the public game only ever sees passwords that expire after a few hours.
const TTL = 6 * 3600;
const cors = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'GET, OPTIONS' };

export default {
  async fetch(req, env) {
    if (req.method === 'OPTIONS') return new Response(null, { headers: cors });
    if (req.method !== 'GET') return new Response('Method not allowed', { status: 405, headers: cors });
    const res = await fetch(`https://rtc.live.cloudflare.com/v1/turn/keys/${env.TURN_KEY_ID}/credentials/generate-ice-servers`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${env.TURN_API_TOKEN}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ ttl: TTL })
    });
    if (!res.ok) return new Response(JSON.stringify({ error: 'relay credentials unavailable' }), { status: 502, headers: { ...cors, 'Content-Type': 'application/json' } });
    const { iceServers } = await res.json();
    // the same shape the game took from Metered: a plain list of ICE servers. Port 53 is left out because
    // browsers refuse it and it only slows the connection down.
    const list = iceServers.map(s => ({ ...s, urls: [].concat(s.urls).filter(u => !/:53\b/.test(u)) })).filter(s => s.urls.length);
    return new Response(JSON.stringify(list), { headers: { ...cors, 'Content-Type': 'application/json', 'Cache-Control': 'no-store' } });
  }
};
