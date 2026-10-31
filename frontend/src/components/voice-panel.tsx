"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@fluentui/react-components";
import { Microphone, MicrophoneSlash, PhoneDisconnect } from "@phosphor-icons/react";
import { OpenAIVoiceCall, type VoiceExchange, type VoiceUpdate } from "@/lib/openai-voice";

export function VoicePanel({ sessionId, disabled = false, onActiveChange }: {
    sessionId: string; disabled?: boolean; onActiveChange?: (active: boolean) => void;
}) {
    const [state, setState] = useState<VoiceUpdate>({ phase: "idle", message: "Nói chuyện với A1 bằng giọng nói OpenAI." });
    const [muted, setMuted] = useState(false);
    const [exchanges, setExchanges] = useState<VoiceExchange[]>([]);
    const audio = useRef<HTMLAudioElement>(null);
    const call = useRef<OpenAIVoiceCall | null>(null);
    const activeCallback = useRef(onActiveChange);
    useEffect(() => { activeCallback.current = onActiveChange; }, [onActiveChange]);
    const generation = useRef(0);
    useEffect(() => () => { generation.current++; void call.current?.stop(); call.current = null; activeCallback.current?.(false); }, [sessionId]);
    const active = !["idle", "error"].includes(state.phase);
    useEffect(() => { if (disabled && call.current) void call.current.stop("Đã dừng voice vì phiên không còn khả dụng."); }, [disabled]);
    async function start() {
        if (disabled || call.current || !audio.current) return;
        setExchanges([]); setMuted(false);
        const attempt = ++generation.current;
        const current = new OpenAIVoiceCall(sessionId, audio.current, update => {
            if (attempt !== generation.current) return;
            setState(update);
            const running = !["idle", "error"].includes(update.phase);
            activeCallback.current?.(running);
            if (!running) call.current = null;
        }, exchange => { if (attempt === generation.current) setExchanges(items => [...items, exchange]); });
        call.current = current;
        await current.start();
    }
    return <section className="voice-panel" aria-label="Nói chuyện bằng giọng nói" style={{ borderTop: "1px solid var(--line)", padding: "10px 14px" }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            {!active ? <Button size="small" icon={<Microphone size={16} />} disabled={disabled} onClick={start}>Nói chuyện với AI</Button> : <><Button size="small" icon={muted ? <MicrophoneSlash size={16} /> : <Microphone size={16} />} onClick={() => { const value = !muted; setMuted(value); call.current?.mute(value); }}>{muted ? "Bật micro" : "Tắt micro"}</Button><Button size="small" icon={<PhoneDisconnect size={16} />} onClick={() => { void call.current?.stop(); }}>Kết thúc voice</Button></>}
            <span role="status" style={{ fontSize: 12 }}>{state.message}</span>
        </div>
        <small>Giọng nói AI · tối đa 4 phút mỗi cuộc gọi · voice không cấp xu.</small>
        <audio ref={audio} autoPlay controls={active} aria-label="Âm thanh phản hồi AI" style={{ width: "100%", height: active ? 28 : 0, display: active ? "block" : "none" }} />
        {!!exchanges.length && <details><summary>Bản ghi cuộc nói chuyện ({exchanges.length} lượt)</summary><div style={{ maxHeight: 160, overflow: "auto", fontSize: 12 }}>{exchanges.map((exchange, index) => <div key={index}><p><b>Bạn:</b> {exchange.question}</p><p><b>A1:</b> {exchange.reply}</p></div>)}</div></details>}
    </section>;
}
