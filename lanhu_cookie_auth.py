#!/usr/bin/env python3
"""Lanhu cookie capture and refresh via Playwright."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import re
import shutil
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


def _ensure_runtime_dependencies() -> None:
    missing = []
    try:
        import httpx  # noqa: F401
    except ImportError:
        missing.append("httpx")
    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except ImportError:
        missing.append("playwright")
    if missing:
        print(
            "Missing Python packages: " + ", ".join(missing),
            file=sys.stderr,
        )
        print(
            "Use the project virtualenv (do not use system python3):\n"
            "  source venv/bin/activate\n"
            "  pip install -r requirements.txt\n"
            "  playwright install chromium\n"
            "  python lanhu_cookie_auth.py --compare",
            file=sys.stderr,
        )
        raise SystemExit(1)


_ensure_runtime_dependencies()

import httpx
from playwright.async_api import async_playwright

PROJECT_ROOT = Path(__file__).parent
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"
DEFAULT_STORAGE_PATH = PROJECT_ROOT / "data" / "lanhu_storage_state.json"
LANHU_HOME_URL = "https://lanhuapp.com/"
LANHU_WEB_ENTRY = "https://lanhuapp.com/web/"
LANHU_PROJECT_URL_EXAMPLE = (
    "https://lanhuapp.com/web/#/item/project/stage?tid=...&pid=..."
)

INVALID_COOKIE_VALUES = frozenset({"", "undefined", "null", "None"})


def system_chrome_available() -> bool:
    """Return True if Google Chrome appears installed on this machine."""
    system = platform.system()
    if system == "Darwin":
        return Path("/Applications/Google Chrome.app").exists()
    if system == "Windows":
        candidates = [
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
            / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
            / "Google/Chrome/Application/chrome.exe",
        ]
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            candidates.append(
                Path(local_app) / "Google/Chrome/Application/chrome.exe"
            )
        return any(path.is_file() for path in candidates)
    return (
        shutil.which("google-chrome") is not None
        or shutil.which("google-chrome-stable") is not None
    )


async def launch_lanhu_browser(playwright, *, headless: bool):
    """Prefer system Google Chrome; fall back to Playwright's bundled Chromium."""
    if system_chrome_available():
        try:
            print("使用本机 Google Chrome")
            return await playwright.chromium.launch(channel="chrome", headless=headless)
        except Exception as exc:
            print(
                f"启动本机 Chrome 失败 ({exc})，改用 Playwright 自带浏览器...",
                file=sys.stderr,
            )
    else:
        print("未检测到本机 Chrome，使用 Playwright 自带浏览器 (Chrome for Testing)")
    return await playwright.chromium.launch(headless=headless)


def parse_cookie_header(cookie_header: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for part in (cookie_header or "").split("; "):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        parsed[name.strip()] = value.strip()
    return parsed


def build_cookie_header(cookie_map: dict[str, str]) -> str:
    return "; ".join(f"{name}={value}" for name, value in cookie_map.items())


def _cookie_domain_rank(domain: str) -> int:
    domain = domain or ""
    if domain == ".lanhuapp.com":
        return 3
    if domain.endswith("lanhuapp.com"):
        return 2
    return 1


def cookies_to_header(cookies: list[dict]) -> str:
    """Merge Playwright cookies into a single Cookie header for Lanhu APIs."""
    best_by_name: dict[str, dict] = {}

    for item in cookies or []:
        domain = item.get("domain", "")
        if "lanhuapp.com" not in domain:
            continue

        name = item.get("name")
        value = item.get("value")
        if not name or value is None:
            continue

        value = str(value).strip()
        if value in INVALID_COOKIE_VALUES:
            continue

        current = best_by_name.get(name)
        if not current:
            best_by_name[name] = item
            continue

        current_value = str(current.get("value", "")).strip()
        current_rank = _cookie_domain_rank(current.get("domain", ""))
        new_rank = _cookie_domain_rank(domain)

        if new_rank > current_rank:
            best_by_name[name] = item
        elif new_rank == current_rank and len(value) > len(current_value):
            best_by_name[name] = item

    preferred_order = (
        "PASSPORT",
        "user_token",
        "session",
        "SERVERID",
        "aliyungf_tc",
        "acw_tc",
    )
    ordered_names = [name for name in preferred_order if name in best_by_name]
    ordered_names.extend(
        sorted(name for name in best_by_name if name not in preferred_order)
    )
    return build_cookie_header(
        {name: str(best_by_name[name].get("value", "")).strip() for name in ordered_names}
    )


def cookie_quality_report(cookie_header: str) -> dict:
    parsed = parse_cookie_header(cookie_header)
    session = parsed.get("session", "")
    user_token = parsed.get("user_token", "")
    passport = parsed.get("PASSPORT", "")
    return {
        "cookieCount": len(parsed),
        "hasPASSPORT": bool(passport),
        "passportLength": len(passport),
        "hasUserToken": bool(user_token) and user_token not in INVALID_COOKIE_VALUES,
        "userTokenLength": len(user_token),
        "sessionLength": len(session),
        "sessionLooksFlask": session.startswith(".eJ"),
    }


def is_valid_lanhu_cookie(cookie_header: str) -> bool:
    """Strict validation: incomplete Playwright captures must be rejected."""
    report = cookie_quality_report(cookie_header)
    if report["cookieCount"] < 4:
        return False
    if not report["hasPASSPORT"] or report["passportLength"] < 20:
        return False
    if not report["hasUserToken"] or report["userTokenLength"] < 50:
        return False
    if report["sessionLength"] < 120:
        return False
    return True


def compare_cookie_headers(existing: str, candidate: str) -> dict:
    old = parse_cookie_header(existing)
    new = parse_cookie_header(candidate)
    all_names = sorted(set(old) | set(new))
    diff = []
    for name in all_names:
        old_val = old.get(name)
        new_val = new.get(name)
        if old_val == new_val:
            status = "same"
        elif old_val is None:
            status = "only_in_candidate"
        elif new_val is None:
            status = "only_in_existing"
        else:
            status = "value_changed"
        diff.append({
            "name": name,
            "status": status,
            "existingLength": len(old_val or ""),
            "candidateLength": len(new_val or ""),
        })
    return {
        "existing": cookie_quality_report(existing),
        "candidate": cookie_quality_report(candidate),
        "existingValid": is_valid_lanhu_cookie(existing),
        "candidateValid": is_valid_lanhu_cookie(candidate),
        "diff": diff,
    }


def merge_cookie_headers(existing: str, candidate: str) -> str:
    """Prefer the stronger auth fields when refreshing cookies."""
    old = parse_cookie_header(existing)
    new = parse_cookie_header(candidate)
    merged = dict(old)

    for name, value in new.items():
        if value in INVALID_COOKIE_VALUES:
            continue
        if name not in merged:
            merged[name] = value
            continue

        if name == "session":
            if len(value) > len(merged[name]):
                merged[name] = value
        elif name == "PASSPORT":
            if len(value) >= len(merged[name]):
                merged[name] = value
        elif name == "user_token":
            if merged[name] in INVALID_COOKIE_VALUES or len(value) > len(merged[name]):
                merged[name] = value
        else:
            merged[name] = value

    return build_cookie_header(merged)


def update_env_lanhu_cookie(env_path: Path, cookie: str) -> None:
    escaped = cookie.replace("\\", "\\\\").replace('"', '\\"')
    new_line = f'LANHU_COOKIE="{escaped}"'
    if env_path.exists():
        content = env_path.read_text(encoding="utf-8")
    else:
        content = ""
    if re.search(r"^LANHU_COOKIE=", content, flags=re.MULTILINE):
        content = re.sub(r"^LANHU_COOKIE=.*$", new_line, content, flags=re.MULTILINE)
    else:
        if content and not content.endswith("\n"):
            content += "\n"
        content += new_line + "\n"
    env_path.write_text(content, encoding="utf-8")


def parse_lanhu_url_params(url: str) -> dict[str, str]:
    if not url:
        return {}
    parsed = urlparse(url)
    query = parsed.query
    if parsed.fragment and "?" in parsed.fragment:
        query = parsed.fragment.split("?", 1)[1]
    params = {k: v[0] for k, v in parse_qs(query).items() if v}
    return params


def resolve_target_urls() -> tuple[str, str]:
    login_url = os.getenv("LANHU_LOGIN_URL", "").strip() or LANHU_WEB_ENTRY
    verify_url = login_url
    if "lanhuapp.com" not in login_url:
        login_url = LANHU_WEB_ENTRY
        verify_url = LANHU_WEB_ENTRY
    return login_url, verify_url


async def verify_cookie_with_api(cookie_header: str, verify_url: str) -> dict:
    params = parse_lanhu_url_params(verify_url)
    project_id = params.get("pid") or params.get("project_id")
    team_id = params.get("tid")
    if not project_id or not team_id:
        return {"skipped": True, "reason": "verify URL has no tid/pid"}

    api_url = (
        "https://lanhuapp.com/api/project/images"
        f"?project_id={project_id}&team_id={team_id}"
        f"&dds_status=1&position=1&show_cb_src=1&comment=1"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://lanhuapp.com/",
        "Cookie": cookie_header,
    }
    async with httpx.AsyncClient(timeout=20.0, headers=headers, follow_redirects=True) as client:
        response = await client.get(api_url)
        body_preview = response.text[:120]
        ok = response.status_code == 200 and '"code":"00000"' in response.text
        return {
            "skipped": False,
            "ok": ok,
            "statusCode": response.status_code,
            "bodyPreview": body_preview,
            "apiUrl": api_url,
        }


async def collect_cookie_header(page, context, verify_url: str) -> str:
    await page.goto(verify_url, wait_until="networkidle", timeout=120000)
    await page.wait_for_timeout(2000)
    return cookies_to_header(await context.cookies())


def wait_for_user_to_continue() -> None:
    """Pause until the user confirms login and project page are ready."""
    print("\n浏览器已打开蓝湖首页。")
    print("  1. 如未登录，请完成登录（扫码 / 账号密码均可）")
    print("  2. 登录后在页面中点击进入你的项目（地址见 .env 中 LANHU_LOGIN_URL），例如：")
    print(f"     {LANHU_PROJECT_URL_EXAMPLE}")
    input("\n进入项目页后，按 Enter 继续抓取 Cookie... ")


async def wait_for_valid_cookie(
    page,
    context,
    verify_url: str,
    timeout_seconds: int,
    *,
    open_project_first: bool = False,
    poll_only: bool = False,
) -> str:
    """Wait until project page cookies include PASSPORT, JWT user_token, and full session."""
    last_report = cookie_quality_report("")
    navigated_to_project = poll_only

    if open_project_first:
        await page.goto(verify_url, wait_until="networkidle", timeout=120000)
        await page.wait_for_timeout(2000)
        navigated_to_project = True

    for elapsed in range(timeout_seconds):
        if not navigated_to_project:
            await asyncio.sleep(1)
            continue

        candidate = cookies_to_header(await context.cookies())
        last_report = cookie_quality_report(candidate)
        if is_valid_lanhu_cookie(candidate):
            api_check = await verify_cookie_with_api(candidate, verify_url)
            if api_check.get("skipped") or api_check.get("ok"):
                return candidate
        await asyncio.sleep(1)

    raise TimeoutError(
        "Timed out waiting for a complete Lanhu login cookie. "
        f"Last capture: {json.dumps(last_report, ensure_ascii=False)}. "
        "Ensure you finish login and can open your project page in the browser."
    )


async def fetch_cookie_interactive(
    env_path: Path,
    storage_path: Path,
    timeout_seconds: int = 300,
    dry_run: bool = False,
) -> str:
    _, verify_url = resolve_target_urls()
    storage_path.parent.mkdir(parents=True, exist_ok=True)

    print("正在打开蓝湖首页...")
    print(f"  1. 浏览器将自动打开: {LANHU_HOME_URL}")
    print("  2. 登录后点击进入项目页（不会自动跳转）")
    print("  3. 进入项目页后在终端按 Enter，开始抓取 Cookie")
    print("  4. 需要 PASSPORT + user_token + 完整 session")
    print(f"  5. 抓取超时: {timeout_seconds}s\n")

    async with async_playwright() as playwright:
        browser = await launch_lanhu_browser(playwright, headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(LANHU_HOME_URL, wait_until="domcontentloaded")
        wait_for_user_to_continue()
        print("\n正在抓取 Cookie...")
        cookie_header = await wait_for_valid_cookie(
            page,
            context,
            verify_url,
            timeout_seconds,
            poll_only=True,
        )
        await context.storage_state(path=str(storage_path))
        await browser.close()

    existing = ""
    if env_path.exists():
        match = re.search(r'^LANHU_COOKIE="([^"]*)"', env_path.read_text(encoding="utf-8"), re.M)
        if match:
            existing = match.group(1)

    if existing:
        comparison = compare_cookie_headers(existing, cookie_header)
        print("\nCookie comparison with current .env:")
        print(json.dumps(comparison, ensure_ascii=False, indent=2))
        cookie_header = merge_cookie_headers(existing, cookie_header)

    if not dry_run:
        update_env_lanhu_cookie(env_path, cookie_header)
    return cookie_header


async def refresh_cookie_from_storage(
    env_path: Path,
    storage_path: Path,
    timeout_seconds: int = 120,
    dry_run: bool = False,
) -> str:
    if not storage_path.exists():
        raise FileNotFoundError(
            f"No saved session at {storage_path}. Run: python lanhu_cookie_auth.py"
        )

    _, verify_url = resolve_target_urls()

    async with async_playwright() as playwright:
        browser = await launch_lanhu_browser(playwright, headless=True)
        context = await browser.new_context(storage_state=str(storage_path))
        page = await context.new_page()
        cookie_header = await wait_for_valid_cookie(
            page,
            context,
            verify_url,
            timeout_seconds,
            open_project_first=True,
        )
        await context.storage_state(path=str(storage_path))
        await browser.close()

    existing = ""
    if env_path.exists():
        match = re.search(r'^LANHU_COOKIE="([^"]*)"', env_path.read_text(encoding="utf-8"), re.M)
        if match:
            existing = match.group(1)
    if existing:
        cookie_header = merge_cookie_headers(existing, cookie_header)

    if not dry_run:
        update_env_lanhu_cookie(env_path, cookie_header)
    return cookie_header


def print_compare_only(env_path: Path, storage_path: Path) -> int:
    existing = ""
    if env_path.exists():
        match = re.search(r'^LANHU_COOKIE="([^"]*)"', env_path.read_text(encoding="utf-8"), re.M)
        if match:
            existing = match.group(1)
    if not existing:
        print("No LANHU_COOKIE found in .env", file=sys.stderr)
        return 1

    if not storage_path.exists():
        print(f"No storage state at {storage_path}", file=sys.stderr)
        return 1

    storage = json.loads(storage_path.read_text(encoding="utf-8"))
    candidate = cookies_to_header(storage.get("cookies", []))
    report = compare_cookie_headers(existing, candidate)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture or refresh Lanhu Cookie via Playwright with strict validation."
    )
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV_PATH)
    parser.add_argument("--storage", type=Path, default=DEFAULT_STORAGE_PATH)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--compare", action="store_true", help="Compare storage vs .env only")
    parser.add_argument("--dry-run", action="store_true", help="Do not write .env")
    return parser.parse_args()


async def main_async() -> int:
    args = parse_args()
    if load_dotenv and DEFAULT_ENV_PATH.exists():
        load_dotenv(DEFAULT_ENV_PATH, override=False)

    if args.compare:
        return print_compare_only(args.env, args.storage)

    try:
        if args.refresh:
            cookie = await refresh_cookie_from_storage(
                args.env, args.storage, args.timeout, dry_run=args.dry_run
            )
            mode = "refreshed"
        else:
            cookie = await fetch_cookie_interactive(
                args.env, args.storage, args.timeout, dry_run=args.dry_run
            )
            mode = "captured"
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    report = cookie_quality_report(cookie)
    api_check = await verify_cookie_with_api(cookie, resolve_target_urls()[1])

    print(f"\nCookie {mode} successfully.")
    print(json.dumps({"quality": report, "apiCheck": api_check}, ensure_ascii=False, indent=2))
    if args.dry_run:
        print("Dry run: .env was not modified.")
    else:
        print(f"  .env updated: {args.env}")
    print(f"  session saved: {args.storage}")
    print(f"  cookie length: {len(cookie)} chars")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
