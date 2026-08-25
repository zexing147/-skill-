#!/usr/bin/env python3
"""Call Douyin's official text anti-dirt endpoint without exposing the token."""
import argparse, json, os, sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ONLINE = "https://developer.toutiao.com/api/v2/tags/text/antidirt"
SANDBOX = "https://open-sandbox.douyin.com/api/v2/tags/text/antidirt"

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--text", required=True)
    p.add_argument("--sandbox", action="store_true")
    args = p.parse_args()
    token = os.environ.get("DOUYIN_ACCESS_TOKEN")
    if not token:
        print(json.dumps({"ok": False, "error": "缺少环境变量 DOUYIN_ACCESS_TOKEN"}, ensure_ascii=False))
        return 2
    body = json.dumps({"tasks": [{"content": args.text}]}).encode("utf-8")
    req = Request(SANDBOX if args.sandbox else ONLINE, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Token", token)
    try:
        with urlopen(req, timeout=30) as response:
            print(json.dumps(json.loads(response.read().decode("utf-8")), ensure_ascii=False, indent=2))
        return 0
    except HTTPError as e:
        print(json.dumps({"ok": False, "http_status": e.code, "error": "接口 HTTP 错误"}, ensure_ascii=False))
        return 1
    except (URLError, TimeoutError) as e:
        detail = e.reason if isinstance(e, URLError) else str(e)
        print(json.dumps({"ok": False, "error": "接口连接失败", "detail": str(detail)}, ensure_ascii=False))
        return 1

if __name__ == "__main__":
    sys.exit(main())
