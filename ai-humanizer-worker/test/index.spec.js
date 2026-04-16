import {
	env,
	createExecutionContext,
	waitOnExecutionContext,
} from "cloudflare:test";
import { describe, it, expect, vi } from "vitest";
import worker from "../src";

describe("AI Humanizer proxy worker", () => {
	it("returns a JSON error when the backend URL is missing", async () => {
		const request = new Request("http://example.com/health");
		const ctx = createExecutionContext();
		const response = await worker.fetch(request, env, ctx);
		await waitOnExecutionContext(ctx);

		expect(response.status).toBe(503);
		await expect(response.json()).resolves.toEqual({
			error: "Backend URL is not configured",
		});
	});

	it("proxies requests to the configured FastAPI backend", async () => {
		const fetchMock = vi
			.spyOn(globalThis, "fetch")
			.mockResolvedValue(
				new Response(JSON.stringify({ status: "ok" }), {
					status: 200,
					headers: { "Content-Type": "application/json" },
				}),
			);

		const request = new Request("http://example.com/v1/plan?fresh=1");
		const response = await worker.fetch(request, {
			...env,
			FASTAPI_BASE_URL: "https://api.example.test",
		});

		expect(fetchMock).toHaveBeenCalledOnce();
		expect(fetchMock.mock.calls[0][0].url).toBe(
			"https://api.example.test/v1/plan?fresh=1",
		);
		expect(response.headers.get("Access-Control-Allow-Origin")).toBe("*");
		await expect(response.json()).resolves.toEqual({ status: "ok" });

		fetchMock.mockRestore();
	});
});
