import urllib.request
import json
import time
import sys

def test(question="مين صممك؟"):
    t0 = time.time()
    payload = {
        "message": question,
        "stream": False
    }
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/v1/conversations/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    resp = urllib.request.urlopen(req)
    total_time = time.time() - t0
    data = json.loads(resp.read().decode("utf-8"))
    
    print(f"Question        : {question}")
    print(f"Total HTTP time : {total_time:.2f}s")
    print(f"LLM Latency     : {data.get('llm_latency_ms')} ms")
    print(f"Model Used      : {data.get('llm_model')}")
    print(f"Reply           : {data.get('reply')}")
    print("-" * 50)

if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "مين صممك؟"
    test(q)
