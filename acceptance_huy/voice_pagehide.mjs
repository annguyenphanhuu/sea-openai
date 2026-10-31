import fs from 'node:fs';
import assert from 'node:assert/strict';

const source = fs.readFileSync('platform_huy/ui_prototype/voice.js', 'utf8');
const {startVoice} = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
const elements = [], events = {}, requests = [];
let resolveMedia, peers = 0, stopped = 0;
globalThis.document = {createElement(tag) {
    const element = {tag, setAttribute() {}, append() {}, pause() {}, scrollIntoView() {}};
    elements.push(element);
    return element;
}};
globalThis.window = {addEventListener(name, callback) {events[name] = callback;}, alert() {}};
globalThis.fetch = async path => {
    requests.push(path);
    return {ok: true, json: async () => ({budget_remaining_usd: 2})};
};
Object.defineProperty(globalThis, 'navigator', {value: {mediaDevices: {
    getUserMedia: () => new Promise(resolve => {resolveMedia = resolve;})
}}});
globalThis.RTCPeerConnection = class {
    constructor() {peers++;}
    addTrack() {}
    createDataChannel() {return {close() {}, readyState: 'closed'};}
    async createOffer() {throw new Error('Unexpected peer after pagehide');}
    close() {}
};
const call = startVoice({sessionId: 'chat-1', button: {insertAdjacentElement() {}}});
elements.find(element => element.tag === 'input').value = 'code';
const pending = elements.filter(element => element.tag === 'button')[0].onclick();
while (!resolveMedia) await new Promise(resolve => setImmediate(resolve));
events.pagehide();
resolveMedia({getTracks: () => [{stop() {stopped++;}}]});
await pending;
assert.equal(peers, 0);
assert.equal(stopped, 1);
assert.equal(call.closed, true);
assert.deepEqual(requests, ['/api/voice/state']);
console.log('PASS pagehide invalidates pending microphone startup; no peer or token created');
