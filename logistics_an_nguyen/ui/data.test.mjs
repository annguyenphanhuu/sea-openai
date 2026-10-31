import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { filterOrders, formatDay, formatInstant, loadOrders, resolveEvidence, validatePayload } from "./data.mjs";

const sample = JSON.parse(await readFile(new URL("../sample_orders.json", import.meta.url), "utf8"));

test("the committed 20-order envelope renders without invented values", () => {
    assert.equal(validatePayload(sample), sample);
    assert.equal(sample.orders.length, 20);
    assert.ok(sample.orders.some((order) => order.revised_eta === null));
    assert.equal(filterOrders(sample.orders, { payment: "COD" }).length, 10);
    assert.equal(filterOrders(sample.orders, { payment: "PREPAID" }).length, 10);
});

test("Vietnam calendar dates and ETA instants remain distinct across midnight", () => {
    assert.equal(formatDay("2026-10-28"), "28/10/2026");
    assert.deepEqual(formatInstant("2026-10-28T17:00:00Z"), { date: "29/10/2026", time: "00:00" });
    assert.deepEqual(formatInstant(null), { date: "Chưa xác định", time: "" });
});

test("search, status and payment filters combine without changing source order", () => {
    const before = JSON.stringify(sample);
    const target = sample.orders.find((order) => order.status === "exception" && order.payment === "COD");
    assert.deepEqual(filterOrders(sample.orders, { search: target.order_id.toLowerCase(), status: "exception", payment: "COD" }), [target]);
    assert.deepEqual(filterOrders(sample.orders, { search: "no-such-order" }), []);
    const late = filterOrders(sample.orders, { sort: "late_days" });
    assert.ok(late.every((order, index) => index === 0 || late[index - 1].late_days >= order.late_days));
    assert.equal(JSON.stringify(sample), before);
});

test("evidence resolves to its original order after UI sorting", () => {
    for (const order of filterOrders(sample.orders, { sort: "priority" })) {
        assert.equal(resolveEvidence(sample, order), order.evidence);
    }
    const broken = structuredClone(sample);
    broken.orders[1].evidence_ref = broken.orders[0].evidence_ref;
    assert.throws(() => validatePayload(broken), /không thuộc đúng đơn/);
    broken.orders[1].evidence_ref = "https://example.invalid/untrusted";
    assert.throws(() => validatePayload(broken), /Tham chiếu/);
});

test("reject duplicate IDs, mixed snapshots and invalid dates", () => {
    for (const mutate of [
        (payload) => { payload.orders[1].order_id = payload.orders[0].order_id; },
        (payload) => { payload.orders[0].assessed_at = "2026-10-29T05:00:00Z"; },
        (payload) => { payload.orders[0].guaranteed_date = "2026-02-31"; },
        (payload) => { payload.orders[0].cause.fault_party = "customer"; },
        (payload) => { payload.orders[0].evidence[0].ingested_at = "2026-10-29T05:00:00Z"; },
    ]) {
        const broken = structuredClone(sample); mutate(broken);
        assert.throws(() => validatePayload(broken), /cấu trúc A2/);
    }
});

test("the sample loader reads the committed file through the shared adapter", async () => {
    const calls = [];
    const payload = await loadOrders({ fetcher: async (url, options) => {
        calls.push([url, options]); return { ok: true, json: async () => sample };
    } });
    assert.equal(payload, sample);
    assert.ok(calls[0][0].endsWith("/sample_orders.json"));
    assert.equal(calls[0][1].credentials, "same-origin");
});

test("API errors are visible and never silently trigger a sample fallback", async () => {
    const calls = [];
    await assert.rejects(loadOrders({ mode: "api", fetcher: async (url) => {
        calls.push(url); return { ok: false, status: 403 };
    } }), /HTTP 403/);
    assert.deepEqual(calls, ["/api/orders"]);
});

test("API success and an empty list use the same validated contract", async () => {
    const empty = { ...sample, orders: [] };
    assert.equal(await loadOrders({ mode: "api", fetcher: async () => ({ ok: true, json: async () => empty }) }), empty);
    await assert.rejects(loadOrders({ mode: "api", fetcher: async () => ({ ok: true, json: async () => ({ orders: [] }) }) }), /cấu trúc A2/);
});
