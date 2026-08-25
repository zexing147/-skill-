from __future__ import annotations

import argparse
import json
import math
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from providers import (BudgetExceeded, ProviderError, create_provider,
                       normalize_account, normalize_comment, normalize_video,
                       resolve_sec_user_id)
from storage import Storage, utc_now
from export_excel import make_xlsx


PAGE_SIZE = 20


def load_accounts(values: list[str], filename: str | None) -> list[str]:
    result = [value.strip() for value in values if value.strip()]
    if filename:
        for line in Path(filename).read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                result.append(line)
    return list(dict.fromkeys(result))


def discounted_cost(requests: int, price: float) -> float:
    # Snapshot of the public tiers on 2026-08-26; override price or verify live before a large run.
    tiers = [(1000, 0.00), (5000, 0.10), (10000, 0.20),
             (20000, 0.30), (30000, 0.40), (math.inf, 0.50)]
    total = 0.0
    lower = 0
    remaining = requests
    for upper, discount in tiers:
        amount = min(remaining, int(upper - lower) if upper != math.inf else remaining)
        total += amount * price * (1 - discount)
        remaining -= amount
        if remaining <= 0:
            break
        lower = int(upper)
    return round(total, 6)


def estimate(account_count: int, videos: int, comments: int, replies: int,
             price_per_call: float) -> dict[str, Any]:
    profile_calls = account_count
    video_pages = account_count * math.ceil(videos / PAGE_SIZE) if videos else 0
    target_videos = account_count * videos
    comment_pages = target_videos * math.ceil(comments / PAGE_SIZE) if comments else 0
    target_comments = target_videos * comments
    reply_pages = target_comments * math.ceil(replies / PAGE_SIZE) if replies else 0
    total = profile_calls + video_pages + comment_pages + reply_pages
    return {
        "accounts": account_count,
        "videos_per_account": videos,
        "comments_per_video": comments,
        "replies_per_comment": replies,
        "profile_calls": profile_calls,
        "video_page_calls": video_pages,
        "comment_page_calls_upper_bound": comment_pages,
        "reply_page_calls_upper_bound": reply_pages,
        "planned_logical_calls": total,
        "estimated_billable_calls": total,
        "estimated_cost_usd": discounted_cost(total, price_per_call),
        "price_assumption_usd_per_success": price_per_call,
        "pricing_snapshot": "2026-08-26; verify current endpoint pricing before large pulls",
        "notes": [
            "Comment and reply estimates are upper bounds based on requested limits.",
            "Retries count against the local call budget but may not be billed by TikHub.",
            "This estimate is not an invoice or confirmed billed amount.",
        ],
    }


def estimate_comments(video_count: int, comments: int, replies: int,
                      price_per_call: float) -> dict[str, Any]:
    comment_pages = video_count * math.ceil(comments / PAGE_SIZE) if comments else 0
    reply_pages = video_count * comments * math.ceil(replies / PAGE_SIZE) if replies else 0
    total = comment_pages + reply_pages
    return {
        "videos_in_database": video_count,
        "comments_per_video": comments,
        "replies_per_comment": replies,
        "comment_page_calls_upper_bound": comment_pages,
        "reply_page_calls_upper_bound": reply_pages,
        "planned_logical_calls": total,
        "estimated_billable_calls": total,
        "estimated_cost_usd": discounted_cost(total, price_per_call),
        "price_assumption_usd_per_success": price_per_call,
        "pricing_snapshot": "2026-08-26; verify current endpoint pricing before large pulls",
        "notes": ["Completed checkpoints can reduce actual calls.",
                  "Estimate is not an invoice or confirmed billed amount."],
    }


def paginate(fetch, limit: int):
    cursor = "0"
    seen_cursors: set[str] = set()
    yielded = 0
    while yielded < limit:
        page = fetch(cursor)
        if not page.items:
            return
        for item in page.items:
            if yielded >= limit:
                return
            yield item
            yielded += 1
        if not page.has_more or not page.next_cursor or page.next_cursor == cursor:
            return
        if page.next_cursor in seen_cursors:
            return
        seen_cursors.add(cursor)
        cursor = page.next_cursor


def write_manifest(output_dir: Path, manifest: dict[str, Any]) -> None:
    content = json.dumps(manifest, ensure_ascii=False, indent=2)
    (output_dir / "manifest.json").write_text(content, encoding="utf-8")
    history_dir = output_dir / "manifests"
    history_dir.mkdir(exist_ok=True)
    (history_dir / f"{manifest['job_id']}.json").write_text(content, encoding="utf-8")


def run_collect(args: argparse.Namespace, accounts: list[str], plan: dict[str, Any]) -> int:
    if args.provider == "tikhub" and not args.enable_paid_provider:
        raise SystemExit("TikHub 付费 Provider 已冻结；只有明确提供 --enable-paid-provider 才会发起请求")
    if args.max_api_calls is None or args.max_api_calls < 1:
        raise SystemExit("collect 必须提供正整数 --max-api-calls；先运行 estimate 并获得用户确认")
    if args.provider == "tikhub" and not os.environ.get("TIKHUB_API_KEY", "").strip():
        raise SystemExit("缺少环境变量 TIKHUB_API_KEY；未发起任何付费请求")
    if plan["estimated_cost_usd"] > args.max_estimated_cost_usd:
        raise SystemExit("估算费用超过 --max-estimated-cost-usd；未发起任何付费请求")
    normalized_accounts: list[tuple[str, str]] = []
    seen_sec_ids: set[str] = set()
    pre_errors: list[dict[str, str]] = []
    for input_ref in accounts:
        try:
            sec_user_id = resolve_sec_user_id(input_ref, timeout=args.timeout)
        except ProviderError as exc:
            print(f"跳过无法解析的账号：{input_ref} ({exc})", file=sys.stderr)
            pre_errors.append({"account": input_ref, "error": str(exc)})
            continue
        if sec_user_id not in seen_sec_ids:
            seen_sec_ids.add(sec_user_id)
            normalized_accounts.append((input_ref, sec_user_id))
    if not normalized_accounts:
        raise SystemExit("没有可解析的账号；未发起任何付费请求")

    provider = create_provider(args.provider, base_url=args.base_url,
                               max_api_calls=args.max_api_calls,
                               timeout=args.timeout, retries=args.retries)
    output_dir = Path(args.output_dir).resolve()
    storage = Storage(output_dir, provider=args.provider)
    job_id = str(uuid.uuid4())
    parameters = {"accounts": accounts, "videos": args.videos, "base_url": args.base_url,
                  "max_estimated_cost_usd": args.max_estimated_cost_usd}
    provider.usage_callback = lambda event: storage.log_usage(job_id, event)
    storage.start_job(job_id, parameters, args.max_api_calls,
                      plan["planned_logical_calls"], plan["estimated_cost_usd"])
    errors: list[dict[str, str]] = list(pre_errors)
    current_videos: list[tuple[int, str]] = []
    stopped_reason: str | None = None

    try:
        for input_ref, sec_user_id in normalized_accounts:
            try:
                profile_raw = provider.get_account(sec_user_id)
                account_id = storage.upsert_account(
                    normalize_account(sec_user_id, profile_raw, input_ref))
                seen_video_ids: set[str] = set()
                for item in paginate(
                    lambda cursor: provider.list_videos(sec_user_id, cursor, PAGE_SIZE), args.videos
                ):
                    video = normalize_video(sec_user_id, item)
                    if not video or video["aweme_id"] in seen_video_ids:
                        continue
                    seen_video_ids.add(video["aweme_id"])
                    video_id = storage.upsert_video(account_id, video)
                    current_videos.append((video_id, video["aweme_id"]))
            except BudgetExceeded:
                raise
            except ProviderError as exc:
                errors.append({"account": input_ref, "error": str(exc)})
                lower = str(exc).lower()
                if any(token in lower for token in ("401", "403", "余额", "balance", "credit", "endpoint")):
                    stopped_reason = f"global_provider_error: {exc}"
                    break

    except BudgetExceeded as exc:
        stopped_reason = str(exc)
    except Exception as exc:  # preserve partial data and a useful manifest
        stopped_reason = f"unexpected_error: {exc}"
        errors.append({"account": "<job>", "error": str(exc)})

    counts = storage.export_csv()
    if stopped_reason or errors:
        status = "partial" if current_videos else "failed"
    else:
        status = "completed"
    storage.finish_job(job_id, status, provider.calls, stopped_reason)
    manifest = {
        "job_id": job_id,
        "provider": args.provider,
        "status": status,
        "requested_scope": parameters,
        "estimated_requests": plan["planned_logical_calls"],
        "max_api_calls": args.max_api_calls,
        "max_estimated_cost_usd": args.max_estimated_cost_usd,
        "actual_requests": provider.calls,
        "estimated_cost_usd": plan["estimated_cost_usd"],
        "reported_billed_cost_usd": None,
        "accounts_requested": len(normalized_accounts),
        "accounts_failed": len(errors),
        "videos_saved_this_run": len(current_videos),
        "database_totals": counts,
        "errors": errors,
        "stopped_reason": stopped_reason,
        "finished_at": utc_now(),
        "excel_file": str(output_dir / "抖音账号研究.xlsx"),
    }
    write_manifest(output_dir, manifest)
    storage.close()
    make_xlsx(output_dir)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if status == "completed" else 2


def run_comment_stage(args: argparse.Namespace, plan: dict[str, Any]) -> int:
    if args.provider == "tikhub" and not args.enable_paid_provider:
        raise SystemExit("TikHub 付费 Provider 已冻结；只有明确提供 --enable-paid-provider 才会发起请求")
    if args.provider == "tikhub" and not os.environ.get("TIKHUB_API_KEY", "").strip():
        raise SystemExit("缺少环境变量 TIKHUB_API_KEY；未发起任何付费请求")
    if plan["estimated_cost_usd"] > args.max_estimated_cost_usd:
        raise SystemExit("估算费用超过 --max-estimated-cost-usd；未发起任何付费请求")
    output_dir = Path(args.output_dir).resolve()
    db_path = output_dir / "douyin-research.sqlite"
    if not db_path.exists():
        raise SystemExit("找不到已有 douyin-research.sqlite；请先运行 collect 抓作品")
    provider = create_provider(args.provider, base_url=args.base_url,
                               max_api_calls=args.max_api_calls,
                               timeout=args.timeout, retries=args.retries)
    storage = Storage(output_dir, provider=args.provider)
    videos = storage.videos()[:args.max_videos]
    if not videos:
        storage.close()
        raise SystemExit("数据库中没有作品；未发起任何付费请求")

    job_id = str(uuid.uuid4())
    parameters = {"stage": "comments", "videos_in_database": len(videos),
                  "comments": args.comments, "replies": args.replies,
                  "refresh": args.refresh, "base_url": args.base_url,
                  "max_estimated_cost_usd": args.max_estimated_cost_usd}
    provider.usage_callback = lambda event: storage.log_usage(job_id, event)
    storage.start_job(job_id, parameters, args.max_api_calls,
                      plan["planned_logical_calls"], plan["estimated_cost_usd"])
    errors: list[dict[str, str]] = []
    stopped_reason: str | None = None
    comments_saved_this_run = 0
    replies_saved_this_run = 0

    try:
        for video_id, aweme_id in videos:
            resource_type = "comments"
            if args.refresh:
                storage.clear_checkpoint(resource_type, aweme_id, args.comments)
            checkpoint = storage.checkpoint(resource_type, aweme_id, args.comments)
            if checkpoint and checkpoint[2] and (checkpoint[1] >= args.comments or checkpoint[3]):
                continue
            cursor, saved = (checkpoint[0], checkpoint[1]) if checkpoint else ("0", 0)
            seen_cursors: set[str] = set()
            while saved < args.comments:
                page = provider.list_comments(aweme_id, cursor)
                page_saved = 0
                for item in page.items:
                    if saved >= args.comments:
                        break
                    comment = normalize_comment(aweme_id, item)
                    if not comment:
                        continue
                    storage.upsert_comment(video_id, comment)
                    saved += 1
                    page_saved += 1
                    comments_saved_this_run += 1
                exhausted = (not page.has_more or not page.next_cursor or page.next_cursor == cursor
                             or page.next_cursor in seen_cursors or page_saved == 0)
                complete = saved >= args.comments or exhausted
                storage.save_checkpoint(resource_type, aweme_id, args.comments,
                                        page.next_cursor or cursor, saved, complete, exhausted)
                if complete:
                    break
                seen_cursors.add(cursor)
                cursor = page.next_cursor

        if args.replies:
            for video_id, aweme_id in videos:
                for comment_id in storage.top_level_comments(video_id, args.comments):
                    resource_type = "replies"
                    resource_id = f"{aweme_id}:{comment_id}"
                    if args.refresh:
                        storage.clear_checkpoint(resource_type, resource_id, args.replies)
                    checkpoint = storage.checkpoint(resource_type, resource_id, args.replies)
                    if checkpoint and checkpoint[2] and (checkpoint[1] >= args.replies or checkpoint[3]):
                        continue
                    cursor, saved = (checkpoint[0], checkpoint[1]) if checkpoint else ("0", 0)
                    seen_cursors: set[str] = set()
                    while saved < args.replies:
                        page = provider.list_replies(aweme_id, comment_id, cursor)
                        page_saved = 0
                        for item in page.items:
                            if saved >= args.replies:
                                break
                            reply = normalize_comment(aweme_id, item, parent_comment_id=comment_id)
                            if not reply:
                                continue
                            storage.upsert_comment(video_id, reply)
                            saved += 1
                            page_saved += 1
                            replies_saved_this_run += 1
                        exhausted = (not page.has_more or not page.next_cursor
                                     or page.next_cursor == cursor
                                     or page.next_cursor in seen_cursors or page_saved == 0)
                        complete = saved >= args.replies or exhausted
                        storage.save_checkpoint(resource_type, resource_id, args.replies,
                                                page.next_cursor or cursor, saved, complete, exhausted)
                        if complete:
                            break
                        seen_cursors.add(cursor)
                        cursor = page.next_cursor
    except BudgetExceeded as exc:
        stopped_reason = str(exc)
    except ProviderError as exc:
        stopped_reason = str(exc)
        errors.append({"resource": "comments", "error": str(exc)})
    except Exception as exc:
        stopped_reason = f"unexpected_error: {exc}"
        errors.append({"resource": "comments", "error": str(exc)})

    counts = storage.export_csv()
    status = "partial" if stopped_reason else "completed"
    storage.finish_job(job_id, status, provider.calls, stopped_reason)
    manifest = {
        "job_id": job_id, "provider": args.provider, "status": status,
        "requested_scope": parameters, "estimated_requests": plan["planned_logical_calls"],
        "max_api_calls": args.max_api_calls, "actual_requests": provider.calls,
        "max_estimated_cost_usd": args.max_estimated_cost_usd,
        "estimated_cost_usd": plan["estimated_cost_usd"],
        "reported_billed_cost_usd": None,
        "comments_saved_this_run": comments_saved_this_run,
        "replies_saved_this_run": replies_saved_this_run,
        "database_totals": counts, "errors": errors,
        "stopped_reason": stopped_reason, "finished_at": utc_now(),
        "excel_file": str(output_dir / "抖音账号研究.xlsx"),
    }
    write_manifest(output_dir, manifest)
    storage.close()
    make_xlsx(output_dir)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if status == "completed" else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Estimate or collect public Douyin account data through TikHub.")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--price-per-call", type=float, default=0.001,
                       help="Estimation assumption only; verify current endpoint price")
        p.add_argument("--output-dir", default="output")
        p.add_argument("--provider", choices=("tikhub", "mediacrawler"),
                       default="mediacrawler", help="数据源；默认本地 mediacrawler")
        p.add_argument("--enable-paid-provider", action="store_true",
                       help="明确允许使用付费 TikHub；未提供时 TikHub 请求会被阻断")

    for command in ("estimate", "collect"):
        p = sub.add_parser(command, help="Estimate or collect accounts and works only")
        p.add_argument("--account", action="append", default=[],
                       help="Homepage URL, share text, or sec_user_id; repeatable")
        p.add_argument("--accounts-file", help="UTF-8 text file, one account per line")
        p.add_argument("--videos", type=int, default=20, help="Max works per account; local default 20")
        add_common(p)
        if command == "collect":
            p.add_argument("--base-url", default="https://api.tikhub.dev")
            p.add_argument("--timeout", type=int, default=60)
            p.add_argument("--retries", type=int, default=3)
            p.add_argument("--max-api-calls", type=int, required=True,
                           help="User-approved hard cap; every HTTP attempt consumes one")
            p.add_argument("--max-estimated-cost-usd", type=float, required=True,
                           help="User-approved cap checked against the current price assumption")

    for command in ("estimate-comments", "collect-comments"):
        p = sub.add_parser(command, help="Estimate or collect comments from an existing database")
        p.add_argument("--comments", type=int, required=True,
                       help="Max top-level comments per video")
        p.add_argument("--max-videos", type=int, required=True,
                       help="Hard cap on videos selected from the existing database")
        p.add_argument("--replies", type=int, default=0,
                       help="Max replies per captured top-level comment")
        add_common(p)
        if command == "collect-comments":
            p.add_argument("--base-url", default="https://api.tikhub.dev")
            p.add_argument("--timeout", type=int, default=60)
            p.add_argument("--retries", type=int, default=3)
            p.add_argument("--refresh", action="store_true",
                           help="Ignore completed checkpoints and fetch from cursor 0")
            p.add_argument("--max-api-calls", type=int, required=True)
            p.add_argument("--max-estimated-cost-usd", type=float, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.price_per_call < 0:
        raise SystemExit("--price-per-call 不能为负数")

    if args.command in ("estimate", "collect"):
        accounts = load_accounts(args.account, args.accounts_file)
        if not accounts:
            raise SystemExit("至少提供一个 --account 或 --accounts-file")
        if not 0 <= args.videos <= 5000:
            raise SystemExit("--videos 必须在 0 到 5000 之间")
        plan = estimate(len(accounts), args.videos, 0, 0, args.price_per_call)
        if args.command == "estimate":
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 0
        if args.timeout <= 0 or args.retries <= 0:
            raise SystemExit("--timeout 和 --retries 必须为正数")
        if args.max_api_calls <= 0 or args.max_estimated_cost_usd < 0:
            raise SystemExit("请求上限必须为正数，估算金额上限不能为负数")
        return run_collect(args, accounts, plan)

    if (not 1 <= args.comments <= 5000 or not 0 <= args.replies <= 1000
            or not 1 <= args.max_videos <= 100000):
        raise SystemExit("--comments 必须在 1 到 5000，--replies 必须在 0 到 1000")
    db_path = Path(args.output_dir).resolve() / "douyin-research.sqlite"
    if not db_path.exists():
        raise SystemExit("找不到已有 douyin-research.sqlite；请先运行 collect")
    storage = Storage(Path(args.output_dir).resolve(), provider=args.provider)
    video_count = len(storage.videos()[:args.max_videos])
    storage.close()
    plan = estimate_comments(video_count, args.comments, args.replies, args.price_per_call)
    if args.command == "estimate-comments":
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    if args.timeout <= 0 or args.retries <= 0:
        raise SystemExit("--timeout 和 --retries 必须为正数")
    if args.max_api_calls <= 0 or args.max_estimated_cost_usd < 0:
        raise SystemExit("请求上限必须为正数，估算金额上限不能为负数")
    return run_comment_stage(args, plan)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("已由用户中止。", file=sys.stderr)
        raise SystemExit(130)
