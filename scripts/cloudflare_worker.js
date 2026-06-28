// Cloudflare Worker that proxies the King of the Hill v4 read-only RPC API.
//
// Deploy this Worker and route `ga.jjjjj.dev/api/*` (or your chosen subdomain/path)
// to it. The static frontend stays on Cloudflare Pages and calls `/api/config`
// and `/api/rpc` same-origin.
//
// Required secrets/environment variables:
//   ALCHEMY_RPC_URL          - full Alchemy endpoint, e.g. https://base-mainnet.g.alchemy.com/v2/KEY
//   KINGOFTHEHILL_ADDRESS    - deployed contract address
//   CHAIN_ID                 - e.g. 8453 for Base mainnet
//
// This Worker caches read-only eth_* calls for 2 seconds so N visitors do not
// create N upstream requests to Alchemy.

const READ_ONLY_METHODS = new Set([
  'eth_call',
  'eth_getLogs',
  'eth_getCode',
  'eth_blockNumber',
  'eth_chainId',
  'net_version',
  'eth_getBalance',
  'eth_getTransactionReceipt',
  'eth_getTransactionByHash',
  'eth_getBlockByNumber',
  'eth_getStorageAt',
  'eth_gasPrice',
  'eth_feeHistory',
  'eth_estimateGas',
]);

const CACHE_SECONDS = 2;

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;

    if (request.method === 'OPTIONS') {
      return handleCors();
    }

    if (path === '/api/config') {
      return jsonResponse(
        {
          contractAddress: env.KINGOFTHEHILL_ADDRESS,
          chainId: parseInt(env.CHAIN_ID || '8453', 10),
          rpcProxyUrl: '/api/rpc',
        },
        200,
        { 'Cache-Control': 'no-store' }
      );
    }

    if (path === '/api/rpc' && request.method === 'POST') {
      const bodyText = await request.text();

      let body;
      try {
        body = JSON.parse(bodyText);
      } catch {
        return jsonResponse(
          { jsonrpc: '2.0', error: { code: -32700, message: 'Parse error' }, id: null },
          400
        );
      }

      // Block state-changing JSON-RPC methods at the edge (including batches).
      const requests = Array.isArray(body) ? body : [body];
      const bad = requests.find((r) => !r || !READ_ONLY_METHODS.has(r.method));
      if (bad) {
        return jsonResponse(
          {
            jsonrpc: '2.0',
            error: { code: -32600, message: `Method not allowed: ${bad?.method || 'unknown'}` },
            id: bad?.id ?? body.id ?? null,
          },
          403
        );
      }

      const cache = caches.default;
      const cacheKey = new Request(
        `${url.origin}${path}?k=${await sha256(bodyText)}`,
        { method: 'GET' }
      );

      const cached = await cache.match(cacheKey);
      if (cached) {
        return cached;
      }

      const upstream = await fetch(env.ALCHEMY_RPC_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: bodyText,
      });

      const response = new Response(upstream.body, {
        status: upstream.status,
        statusText: upstream.statusText,
        headers: {
          'Content-Type': 'application/json',
          'Cache-Control': `public, max-age=${CACHE_SECONDS}`,
          'Access-Control-Allow-Origin': '*',
        },
      });

      ctx.waitUntil(cache.put(cacheKey, response.clone()));
      return response;
    }

    return new Response('Not found', { status: 404 });
  },
};

function jsonResponse(obj, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { 'Content-Type': 'application/json', ...extraHeaders },
  });
}

function handleCors() {
  return new Response(null, {
    status: 204,
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    },
  });
}

async function sha256(message) {
  const encoder = new TextEncoder();
  const data = encoder.encode(message);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  return Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}
