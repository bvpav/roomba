import asyncio
import json
import os
import cv2
import numpy as np
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription

ROOT = os.path.dirname(__file__)

# Track peer connections for cleanup
pcs = set()

# Store the current peer connection globally for the SPSC POC
# In a real app, you'd use a session ID
current_pc = None

async def offer(request):
    global current_pc
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    current_pc = pc
    pcs.add(pc)

    @pc.on("track")
    def on_track(track):
        print(f"Track {track.kind} received")
        if track.kind == "video":
            async def process_video():
                print("Starting video processing loop...")
                count = 0
                while True:
                    try:
                        frame = await track.recv()
                        count += 1
                        img = frame.to_ndarray(format="bgr24")
                        if count % 30 == 0:
                            h, w = img.shape[:2]
                            print(f"Received frame {count}: {w}x{h} px")
                            if count == 30:
                                cv2.imwrite("last_frame.jpg", img)
                                print("Saved test frame to 'last_frame.jpg'")
                    except Exception as e:
                        print(f"Video track error/end: {e}")
                        break
            asyncio.ensure_future(process_video())

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        print(f"Connection state is {pc.connectionState}")
        if pc.connectionState == "failed":
            await pc.close()
            pcs.discard(pc)

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.Response(
        content_type="application/json",
        text=json.dumps({
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type
        })
    )

async def add_candidate(request):
    global current_pc
    if current_pc:
        params = await request.json()
        print(f"Received candidate: {params.get('candidate', 'no candidate string')}")
        from aiortc import RTCIceCandidate
        candidate = RTCIceCandidate(
            component=params["component"],
            foundation=params["foundation"],
            ip=params["ip"],
            port=params["port"],
            priority=params["priority"],
            protocol=params["protocol"],
            type=params["type"],
            sdpMid=params["sdpMid"],
            sdpMLineIndex=params["sdpMLineIndex"]
        )
        await current_pc.addIceCandidate(candidate)
        return web.Response(text="OK")
    return web.Response(status=404)

async def index(request):
    content = open(os.path.join(ROOT, "index.html"), "r").read()
    return web.Response(content_type="text/html", text=content)

async def on_shutdown(app):
    # Close all peer connections
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()

if __name__ == "__main__":
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_post("/offer", offer)
    app.router.add_post("/candidate", add_candidate)
    app.on_shutdown.append(on_shutdown)
    
    print("Starting WebRTC Video Server on http://0.0.0.0:8080")
    web.run_app(app, port=8080)
