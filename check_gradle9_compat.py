#!/usr/bin/env python3

# Based on a script by
# Amr Eniou (amrgetment) amorenew@gmail.com

import json
import os
import re
import sys
from pathlib import Path
from typing import List, Tuple, Dict

# MARK: ANSI Colors

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

RED = "\033[31m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
BLUE = "\033[34m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"

# MARK: Color Support
def supports_color() -> bool:
    if os.name == "nt":
        # Windows terminals vary; keep it simple:
        return False
    return sys.stdout.isatty()

USE_COLOR = supports_color()

def c(txt: str, color: str) -> str:
    if not USE_COLOR:
        return txt
    return f"{color}{txt}{RESET}"

def badge(sev: str) -> str:
    # sev: "HIGH" | "WARN" | "INFO"
    if sev == "HIGH":
        return c("🚨 HIGH", RED) if USE_COLOR else "🚨 HIGH"
    if sev == "WARN":
        return c("⚠️  WARN", YELLOW) if USE_COLOR else "⚠️  WARN"
    return c("ℹ️  INFO", BLUE) if USE_COLOR else "ℹ️  INFO"

# MARK: Helpers
def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""

def find_files(root: Path, patterns: Tuple[str, ...]) -> List[Path]:
    out: List[Path] = []
    for pat in patterns:
        out.extend(root.rglob(pat))
    # de-dup
    seen = set()
    uniq = []
    for p in out:
        if p not in seen:
            uniq.append(p)
            seen.add(p)
    return uniq

def short_path(p: Path, project_root: Path) -> str:
    """Make paths shorter for nicer output."""
    try:
        rel = p.relative_to(project_root)
        return str(rel)
    except Exception:
        s = str(p)
        # shrink pub cache long paths
        s = s.replace(str(Path.home()), "~")
        return s

def divider(char="─", width=72) -> str:
    return char * width

def title_box(text: str) -> None:
    print()
    print(c(divider("━"), MAGENTA))
    print(c(f"  {text}", MAGENTA))
    print(c(divider("━"), MAGENTA))
    print()

def section(text: str) -> None:
    print(c(f"\n{text}", CYAN))

def get_pub_cache_dir() -> Path:
    env = os.environ.get("PUB_CACHE")
    if env:
        return Path(env).expanduser()
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / "Pub" / "Cache"
        return Path.home() / "AppData" / "Local" / "Pub" / "Cache"
    return Path.home() / ".pub-cache"

# MARK: Rules
# (title, pattern, advice, sev)
RULES: List[Tuple[str, re.Pattern, str, str]] = [
    ("Deprecated 'maven' plugin", re.compile(r"apply\s+plugin:\s*['\"]maven['\"]"),
     "Replace with 'maven-publish'.", "HIGH"),

    ("Deprecated 'compile' configuration", re.compile(r"(^|\s)compile(\s|\()", re.MULTILINE),
     "Use 'implementation' or 'api'.", "HIGH"),

    ("Deprecated 'provided' configuration", re.compile(r"(^|\s)provided(\s|\()", re.MULTILINE),
     "Use 'compileOnly'.", "HIGH"),

    ("JCenter repository", re.compile(r"jcenter\s*\("),
     "Remove jcenter(); use mavenCentral() + google().", "HIGH"),

    ("Kotlin Android Extensions plugin", re.compile(r"kotlin-android-extensions"),
     "Removed; switch to ViewBinding / kotlin-parcelize.", "HIGH"),

    ("Old AGP classpath (<8)", re.compile(r"classpath\s+['\"]com\.android\.tools\.build:gradle:(\d+)\."),
     "Upgrade AGP to 8+ (Gradle 9 readiness).", "HIGH"),

    ("Old Kotlin plugin (<1.9)", re.compile(r"classpath\s+['\"]org\.jetbrains\.kotlin:kotlin-gradle-plugin:(\d+)\.(\d+)"),
     "Consider Kotlin 1.9+ depending on AGP.", "WARN"),

    ("Legacy buildscript{} style", re.compile(r"^\s*buildscript\s*\{", re.MULTILINE),
     "Not wrong, but modern projects prefer plugins{} / version catalogs.", "INFO"),
]

WRAPPER_RE = re.compile(r"distributionUrl=.*gradle-([0-9.]+)-")

def scan_text_for_rules(text: str) -> List[Tuple[str, str, str]]:
    hits = []
    for title, pattern, advice, sev in RULES:
        m = pattern.search(text)
        if not m:
            continue

        # Version threshold checks
        if title.startswith("Old AGP classpath"):
            major = int(m.group(1))
            if major >= 8:
                continue

        if title.startswith("Old Kotlin plugin"):
            major = int(m.group(1))
            minor = int(m.group(2))
            if (major > 1) or (major == 1 and minor >= 9):
                continue

        hits.append((sev, title, advice))

    return hits

def parse_plugins(project_root: Path) -> List[Dict]:
    f = project_root / ".flutter-plugins-dependencies"
    if not f.exists():
        return []

    try:
        data = json.loads(read_text(f))
    except Exception:
        return []

    plugins = data.get("plugins", {}).get("android", []) or []
    out = []
    for p in plugins:
        name = p.get("name")
        path = p.get("path")
        if name and path:
            out.append({"name": name, "path": path})
    return out

# MARK: Output "Cards"
def print_file_card(file_path: str, issues: List[Tuple[str, str, str]]):
    # file header
    print(c("  ┌──────────────────────────────────────────────────────────────", DIM))
    print(f"  │ 📄 {c(file_path, BOLD if USE_COLOR else '')}")
    print(c("  ├──────────────────────────────────────────────────────────────", DIM))

    for sev, title, advice in issues:
        print(f"  │ {badge(sev)}  {title}")
        print(f"  │    ↳ {c(advice, DIM)}")

    print(c("  └──────────────────────────────────────────────────────────────", DIM))
    print()

def print_plugin_card(plugin_name: str, plugin_path: str, total_issues: int):
    label = f"🔌 {plugin_name}"
    right = f"{total_issues} issue(s)"
    print(c(divider("─"), DIM))
    print(f"{c(label, BOLD if USE_COLOR else '')}  {c('•', DIM)}  {c(plugin_path, DIM)}")
    print(f"{c('↳', DIM)} {c(right, YELLOW if USE_COLOR else '')}")
    print(c(divider("─"), DIM))

# MARK: Main
def main():
    root = Path.cwd()
    if not (root / "pubspec.yaml").exists():
        print("❌ Run this script from your Flutter project root (pubspec.yaml).")
        sys.exit(1)

    android_dir = root / "android"
    if not android_dir.exists():
        print("❌ No android/ folder found.")
        sys.exit(1)

    title_box("🧪 Gradle 9 Compatibility Report (Flutter Android)")

    # ----- Project scan -----
    project_findings = []
    android_files = find_files(
        android_dir,
        ("*.gradle", "*.gradle.kts", "gradle.properties", "settings.gradle", "settings.gradle.kts")
    )
    for f in android_files:
        txt = read_text(f)
        hits = scan_text_for_rules(txt)
        if hits:
            project_findings.append((f, hits))

    wrapper = android_dir / "gradle" / "wrapper" / "gradle-wrapper.properties"
    wrapper_version = None
    if wrapper.exists():
        m = WRAPPER_RE.search(read_text(wrapper))
        if m:
            wrapper_version = m.group(1)

    # ----- Plugin scan -----
    plugin_findings = []
    plugins = parse_plugins(root)
    pub_cache = get_pub_cache_dir()

    for p in plugins:
        name = p["name"]
        base = Path(p["path"]).expanduser()

        if not base.exists():
            # best-effort fallback
            candidates = list(pub_cache.rglob(f"{name}-*"))
            if candidates:
                base = candidates[0]

        android_sub = base / "android"
        if not android_sub.exists():
            continue

        plugin_files = find_files(
            android_sub,
            ("*.gradle", "*.gradle.kts", "gradle.properties", "settings.gradle", "settings.gradle.kts")
        )

        hits_per_file = []
        for f in plugin_files:
            hits = scan_text_for_rules(read_text(f))
            if hits:
                hits_per_file.append((f, hits))

        if hits_per_file:
            plugin_findings.append((name, base, hits_per_file))

    # ----- Summary -----
    total_project = sum(len(h) for _, h in project_findings)
    total_plugins = sum(len(hits) for _, _, files in plugin_findings for _, hits in files)
    total = total_project + total_plugins

    print("📌 Summary")
    print(f"  {c('•', DIM)} Project findings : {c(str(total_project), YELLOW if total_project else GREEN)}")
    print(f"  {c('•', DIM)} Plugin findings  : {c(str(total_plugins), YELLOW if total_plugins else GREEN)}")
    print(f"  {c('•', DIM)} Total            : {c(str(total), RED if total else GREEN)}")
    if wrapper_version:
        print(f"  {c('•', DIM)} Gradle wrapper   : {c(wrapper_version, CYAN)}")
    print()

    # ----- Print project -----
    section("🏗️ Project (android/)")
    if not project_findings:
        print(c("✅ Looks clean. No obvious Gradle 9 blockers found in project files.\n", GREEN))
    else:
        for f, hits in project_findings:
            print_file_card(short_path(f, root), hits)

    # ----- Print plugins -----
    section("🧩 Flutter Plugins")
    if not plugin_findings:
        print(c("✅ No obvious Gradle 9 issues found inside plugins.\n", GREEN))
    else:
        for plugin_name, plugin_path, files in plugin_findings:
            plugin_path_str = str(plugin_path).replace(str(Path.home()), "~")
            total_issues = sum(len(h) for _, h in files)

            print_plugin_card(plugin_name, plugin_path_str, total_issues)

            for f, hits in files:
                # shorten file path by showing only last parts
                fp = str(f).replace(str(Path.home()), "~")
                print_file_card(fp, hits)

    # ----- Exit code -----
    print(c("✅ Next steps:", CYAN))
    print("  1) Update flagged plugins (pub.dev).")
    print("  2) If plugin is abandoned → replace/fork.")
    print("  3) Test build with Gradle 9 wrapper:")
    print("     cd android && ./gradlew tasks")
    print()

    sys.exit(1 if total > 0 else 0)

if __name__ == "__main__":
    main()
