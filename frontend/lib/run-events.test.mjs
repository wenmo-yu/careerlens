import assert from "node:assert/strict";
import { readRunEvents, RunEventProtocolError } from "./run-events.ts";

const event = { run_id: "run", seq: 3, event_type: "step.succeeded", data: { step: "核验" } };
const source = new TextEncoder().encode(
  `: heartbeat\r\n\r\nid: 3\r\nevent: run\r\ndata: ${JSON.stringify(event)}\r\n\r\n` +
  `id: 4\nevent: run\ndata: ${JSON.stringify({ ...event, seq: 4 })}\n\n`,
);
const stream = new ReadableStream({
  start(controller) {
    for (let offset = 0; offset < source.length; offset += 2) {
      controller.enqueue(source.slice(offset, offset + 2));
    }
    controller.close();
  },
});
const got = [];
await readRunEvents(stream, (item) => got.push(item));
assert.deepEqual(got, [event, { ...event, seq: 4 }]);

function eventStream(text) {
  return new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(text));
      controller.close();
    },
  });
}

const final = [];
await readRunEvents(eventStream(`id: 3\r\ndata: ${JSON.stringify(event)}`), (item) => final.push(item));
assert.deepEqual(final, [event]);
await assert.rejects(readRunEvents(
  eventStream(`id: 4\r\ndata: ${JSON.stringify(event)}\r\n\r\n`),
  () => assert.fail("An invalid event must not advance the cursor"),
), RunEventProtocolError);
await assert.rejects(readRunEvents(
  eventStream("data: {broken-json\n\n"), () => assert.fail("Invalid JSON must not be delivered"),
), RunEventProtocolError);
console.log("run progress streaming tests passed");
