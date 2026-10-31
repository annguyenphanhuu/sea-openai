import { z } from "zod";

export const voiceOperationSchema = z.enum(["state", "create", "turn", "end"]);
const identifier = z.string().min(1).max(256);
export const voicePayloads = {
    state: z.object({}).strict(),
    create: z.object({ session_id: identifier, request_id: z.string().uuid() }).strict(),
    turn: z.object({ session_id: identifier, voice_session_id: identifier, text: z.string().trim().min(1).max(6000), request_id: z.string().min(1).max(200) }).strict(),
    end: z.object({ voice_session_id: identifier }).strict(),
};
const budget = z.object({ budget_remaining_usd: z.number(), provider_billing_cap: z.literal(false).optional() });
export const voiceResults = {
    state: budget.extend({ available: z.boolean(), max_duration_seconds: z.number() }),
    create: z.object({ voice_session_id: identifier, care_session_id: identifier, client_secret: z.string().startsWith("ek_"), expires_at: z.number(), max_duration_seconds: z.number().positive(), deadline_at: z.number() }),
    turn: z.object({ reply: z.string(), inside: z.object({ channel: z.literal("voice"), codes: z.array(z.string()) }), status: z.string() }),
    end: budget.extend({ status: z.literal("ended") }),
};
export type VoiceCredential = z.infer<typeof voiceResults.create>;
export async function voiceApi<K extends keyof typeof voicePayloads>(operation: K, payload: z.input<(typeof voicePayloads)[K]>) {
    const response = await fetch(`/api/voice/${operation}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload), cache: "no-store", signal: AbortSignal.timeout(30000) });
    const body: unknown = await response.json();
    if (!response.ok) {
        const error = z.object({ error: z.string() }).safeParse(body);
        throw new Error(error.success ? error.data.error : "Voice chưa sẵn sàng.");
    }
    return body;
}
