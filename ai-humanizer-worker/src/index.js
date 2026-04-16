export default {
	async fetch(request, env) {
	  const url = new URL(request.url);
  
	  // ✅ CORS headers (important for RapidAPI)
	  const headers = {
		"Content-Type": "application/json",
		"Access-Control-Allow-Origin": "*",
		"Access-Control-Allow-Methods": "GET, POST, OPTIONS",
		"Access-Control-Allow-Headers": "*"
	  };
  
	  // ✅ Handle preflight
	  if (request.method === "OPTIONS") {
		return new Response(null, { headers });
	  }
  
	  // 🔐 API KEY PROTECTION
	  const apiKey = request.headers.get("x-api-key");
  
	  if (apiKey !== env.MY_API_KEY) {
		return new Response(JSON.stringify({ error: "Unauthorized" }), {
		  status: 401,
		  headers
		});
	  }
  
	  // ✅ Health check
	  if (url.pathname === "/") {
		return new Response(JSON.stringify({ status: "API running" }), {
		  headers
		});
	  }
  
	  // 🚀 MAIN ENDPOINT
	  if (url.pathname === "/humanize" && request.method === "POST") {
		try {
		  const body = await request.json();
  
		  if (!body.text) {
			return new Response(JSON.stringify({ error: "Text is required" }), {
			  status: 400,
			  headers
			});
		  }
  
		  // 🤖 Claude API call
		  const response = await fetch("https://api.anthropic.com/v1/messages", {
			method: "POST",
			headers: {
			  "x-api-key": env.ANTHROPIC_API_KEY,
			  "anthropic-version": "2023-06-01",
			  "Content-Type": "application/json"
			},
			body: JSON.stringify({
			  model: "claude-3-haiku-20240307",
			  max_tokens: 300,
			  messages: [
				{
				  role: "user",
				  content: `Rewrite this text to sound human and natural:\n\n${body.text}`
				}
			  ]
			})
		  });
  
		  const data = await response.json();
  
		  const output = data.content?.[0]?.text || "No response";
  
		  return new Response(JSON.stringify({ output }), {
			headers
		  });
  
		} catch (err) {
		  return new Response(JSON.stringify({ error: err.message }), {
			status: 500,
			headers
		  });
		}
	  }
  
	  // ❌ Not found
	  return new Response(JSON.stringify({ error: "Not Found" }), {
		status: 404,
		headers
	  });
	}
  };