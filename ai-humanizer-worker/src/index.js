const CORS_HEADERS = {
	"Access-Control-Allow-Origin": "*",
	"Access-Control-Allow-Methods": "GET, POST, OPTIONS",
	"Access-Control-Allow-Headers": "*",
};

function jsonResponse(body, init = {}) {
	return new Response(JSON.stringify(body), {
		...init,
		headers: {
			"Content-Type": "application/json",
			...CORS_HEADERS,
			...(init.headers || {}),
		},
	});
}

function backendUrlFor(request, env) {
	const baseUrl = env.FASTAPI_BASE_URL || env.BACKEND_URL;
	if (!baseUrl) {
		return null;
	}

	const incoming = new URL(request.url);
	const target = new URL(incoming.pathname + incoming.search, baseUrl);
	return target.toString();
}

export default {
	async fetch(request, env) {
		if (request.method === "OPTIONS") {
			return new Response(null, { headers: CORS_HEADERS });
		}

		const targetUrl = backendUrlFor(request, env);
		if (!targetUrl) {
			return jsonResponse(
				{ error: "Backend URL is not configured" },
				{ status: 503 },
			);
		}

		const proxiedRequest = new Request(targetUrl, request);
		const response = await fetch(proxiedRequest);
		const headers = new Headers(response.headers);

		for (const [key, value] of Object.entries(CORS_HEADERS)) {
			headers.set(key, value);
		}

		return new Response(response.body, {
			status: response.status,
			statusText: response.statusText,
			headers,
		});
	},
};
