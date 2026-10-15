#!/usr/bin/env python3
"""
scan_repo.py — 코드베이스 1차 정찰 (결정적, LLM 없이)

에이전트가 탐색을 시작할 '지도'를 만든다. 결과는 사실(파일:라인 근거 포함)만 담고,
해석(어떤 노드/간선으로 볼지)은 system-explorer 에이전트가 한다.

수집 항목
  - 구조: 디렉터리 트리 요약, 빌드 파일(Gradle/Maven/npm/pip/go), 멀티모듈
  - 런타임 구성: docker-compose 서비스, k8s 리소스, Dockerfile, CI 워크플로
  - 진입점: Spring(@RestController, @*Mapping, @KafkaListener, @RabbitListener, @Scheduled, @FeignClient),
            FastAPI/Flask 라우트, Express 라우트, Celery 태스크
  - 외부 연결: 설정 파일의 datasource/redis/kafka/rabbit/s3/url, 코드 내 http(s) URL, HTTP 클라이언트 사용처
  - 워크플로: git 커밋 이력 요약(기간, 주요 메시지, 많이 바뀐 경로)

사용: python3 scan_repo.py <repo> [-o scan.json] [--max 60]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "build", "dist", "target", ".gradle", ".idea", ".venv", "venv", "__pycache__",
             ".next", ".nuxt", "out", "coverage", ".mypy_cache", ".pytest_cache", "vendor", ".terraform"}
CODE_EXT = {".java", ".kt", ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".jsp", ".cs", ".rb", ".php", ".R", ".r"}
CONF_NAMES = re.compile(r"^(application|bootstrap)[-\w]*\.(ya?ml|properties)$|^\.env(\.\w+)?$|^settings\.py$|^config\.(ya?ml|json|toml)$")

PATTERNS = {
    "spring_controller": re.compile(r"@(Rest)?Controller\b"),
    "spring_mapping": re.compile(r"@(Get|Post|Put|Delete|Patch|Request)Mapping\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?\{?\s*\"([^\"]*)\""),
    "spring_mapping_bare": re.compile(r"@(Get|Post|Put|Delete|Patch)Mapping\s*(?:\(\s*\))?\s*$"),
    "kafka_listener": re.compile(r"@KafkaListener\s*\(([^)]*)\)"),
    "rabbit_listener": re.compile(r"@RabbitListener\s*\(([^)]*)\)"),
    "scheduled": re.compile(r"@Scheduled\s*\(([^)]*)\)"),
    "feign": re.compile(r"@FeignClient\s*\(([^)]*)\)"),
    "kafka_send": re.compile(r"kafkaTemplate\s*\.\s*send\s*\(\s*\"?([\w.\-${}]+)"),
    "http_client_java": re.compile(r"\b(RestTemplate|WebClient|RestClient|HttpClient|OkHttpClient|restTemplate|webClient|restClient)\b"),
    "js_http": re.compile(r"\b(fetch\s*\(|axios\.|EventSource\s*\(|new WebSocket\s*\()"),
    "object_storage": re.compile(r"\b(boto3|S3Client|S3Presigner|S3AsyncClient|AmazonS3|MinioClient|get_object|put_object|upload_file|BlobServiceClient|Storage\.)"),
    "messaging": re.compile(r"\b(AIOKafkaConsumer|AIOKafkaProducer|KafkaConsumer|KafkaProducer|confluent_kafka|aio_pika|pika\.|RabbitTemplate|StreamListener|redis\.publish|\.xadd\(|producer\.send\s*\()"),
    "jpa_repo": re.compile(r"interface\s+(\w+)\s+extends\s+(JpaRepository|CrudRepository|MongoRepository|R2dbcRepository)"),
    "mybatis_mapper": re.compile(r"@Mapper\b"),
    "fastapi_route": re.compile(r"@(\w+)\.(get|post|put|delete|patch|websocket)\s*\(\s*[\"']([^\"']*)"),
    "fastapi_router_prefix": re.compile(r"APIRouter\s*\(([^)]*)\)"),
    "include_router": re.compile(r"include_router\s*\(([^)]*)\)"),
    "flask_route": re.compile(r"@(\w+)\.route\s*\(\s*[\"']([^\"']*)"),
    "express_route": re.compile(r"\b(app|router)\.(get|post|put|delete|patch)\s*\(\s*[\"'`]([^\"'`]*)"),
    "celery_task": re.compile(r"@(\w+\.)?(shared_)?task\b"),
    "py_http": re.compile(r"\b(requests|httpx|aiohttp)\.(get|post|put|delete|AsyncClient|Client|ClientSession)\b"),
    "subprocess": re.compile(r"\b(subprocess\.(run|Popen|call)|ProcessBuilder|Runtime\.getRuntime\(\)\.exec|Command::new)\b"),
    "llm_sdk": re.compile(r"\b(anthropic|openai|langchain|langgraph|llama_index|ChatAnthropic|ChatOpenAI|spring\.ai)\b"),
    "sse_ws": re.compile(r"\b(SseEmitter|WebSocketHandler|@ServerEndpoint|EventSource|StreamingResponse|websocket)\b"),
    "url": re.compile(r"https?://[\w\-.:@]+[\w/\-.%?=&]*"),
}
CONF_KEYS = re.compile(
    r"(datasource|jdbc:|r2dbc:|mongodb|redis|kafka|bootstrap-servers|rabbit|amqp|s3|bucket|minio|elasticsearch|"
    r"opensearch|smtp|mail\.host|slack|webhook|api[-_.]?url|base[-_.]?url|endpoint|host|DATABASE_URL|REDIS_URL|BROKER)",
    re.I,
)
URL_NOISE = re.compile(r"(w3\.org|apache\.org/licenses|schemas?\.|xmlns|springframework\.org/schema|example\.com|localhost:?\d*/?$|github\.com/[\w-]+/[\w-]+/(blob|issues))")


def walk(root: Path):
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS and not d.startswith(".") or d in (".github",)]
        for f in fns:
            yield Path(dp) / f


def rel(p: Path, root: Path) -> str:
    return str(p.relative_to(root))


def tree(root: Path, depth: int = 3, max_entries: int = 25) -> list[str]:
    out = []

    def rec(d: Path, lvl: int):
        if lvl > depth:
            return
        try:
            items = sorted(d.iterdir(), key=lambda x: (x.is_file(), x.name))
        except PermissionError:
            return
        items = [i for i in items if i.name not in SKIP_DIRS and not (i.name.startswith(".") and i.name != ".github")]
        for k, i in enumerate(items):
            if k >= max_entries:
                out.append("  " * lvl + f"… (+{len(items) - max_entries})")
                break
            out.append("  " * lvl + i.name + ("/" if i.is_dir() else ""))
            if i.is_dir():
                rec(i, lvl + 1)

    rec(root, 0)
    return out[:400]


def git_summary(root: Path) -> dict:
    def run(*args):
        try:
            return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=30).stdout
        except Exception:
            return ""

    if not run("rev-parse", "--is-inside-work-tree").strip():
        return {}
    log = run("log", "--no-merges", "--date=short", "--pretty=%ad\t%an\t%s", "-n", "400").strip().splitlines()
    if not log:
        return {}
    churn = Counter()
    for line in run("log", "--no-merges", "--name-only", "--pretty=", "-n", "400").splitlines():
        if line.strip():
            parts = line.split("/")
            churn["/".join(parts[:2]) if len(parts) > 2 else parts[0]] += 1
    by_month = Counter(l.split("\t")[0][:7] for l in log)
    authors = Counter(l.split("\t")[1] for l in log if "\t" in l)
    return {
        "first_commit": log[-1].split("\t")[0],
        "last_commit": log[0].split("\t")[0],
        "commits_sampled": len(log),
        "commits_by_month": dict(sorted(by_month.items())),
        "authors": dict(authors.most_common(8)),
        "recent_subjects": [l.split("\t")[-1] for l in log[:40]],
        "oldest_subjects": [l.split("\t")[-1] for l in log[-15:]][::-1],
        "hot_paths": dict(churn.most_common(20)),
        "tags": run("tag", "--sort=-creatordate").split()[:15],
    }


def parse_compose(p: Path) -> list[dict]:
    try:
        import yaml  # type: ignore
        doc = yaml.safe_load(p.read_text(encoding="utf-8", errors="ignore")) or {}
        svcs = doc.get("services", {}) or {}
        out = []
        for name, s in svcs.items():
            s = s or {}
            dep = s.get("depends_on", [])
            if isinstance(dep, dict):
                dep = list(dep)
            env = s.get("environment", {})
            if isinstance(env, list):
                env = dict(x.split("=", 1) if "=" in x else (x, "") for x in env)
            out.append({
                "service": name,
                "image": s.get("image"),
                "build": s.get("build") if isinstance(s.get("build"), str) else (s.get("build") or {}).get("context") if s.get("build") else None,
                "ports": s.get("ports"),
                "depends_on": dep,
                "env_keys_hint": {k: v for k, v in (env or {}).items() if CONF_KEYS.search(k) or CONF_KEYS.search(str(v))},
            })
        return out
    except Exception:
        names = re.findall(r"^\s{2}([\w\-]+):\s*$", p.read_text(encoding="utf-8", errors="ignore"), re.M)
        return [{"service": n} for n in names]


def scan(root: Path, cap: int) -> dict:
    res: dict = {
        "root": str(root),
        "tree": tree(root),
        "readme": None,
        "build": [],
        "runtime": {"compose": [], "dockerfiles": [], "k8s": [], "ci": []},
        "entrypoints": defaultdict(list),
        "integrations": defaultdict(list),
        "config_hints": [],
        "urls": Counter(),
        "languages": Counter(),
    }
    for p in walk(root):
        r = rel(p, root)
        name = p.name
        try:
            size = p.stat().st_size
        except OSError:
            continue
        if size > 1_500_000:
            continue
        low = name.lower()
        if low in ("readme.md", "readme") and res["readme"] is None and p.parent == root:
            res["readme"] = p.read_text(encoding="utf-8", errors="ignore")[:3000]
        if name in ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts", "pom.xml",
                    "package.json", "requirements.txt", "pyproject.toml", "go.mod", "Cargo.toml", "DESCRIPTION"):
            txt = p.read_text(encoding="utf-8", errors="ignore")
            deps = []
            if name.startswith("build.gradle"):
                deps = re.findall(r"(?:implementation|api|runtimeOnly|compileOnly)\s*\(?[\"']([^\"']+)[\"']", txt)
            elif name.startswith("settings.gradle"):
                deps = re.findall(r"include\s*\(?\s*([^\n)]+)", txt)
            elif name == "pom.xml":
                deps = re.findall(r"<artifactId>([^<]+)</artifactId>", txt)
            elif name == "package.json":
                try:
                    j = json.loads(txt)
                    deps = list((j.get("dependencies") or {}).keys())
                except Exception:
                    pass
            elif name == "requirements.txt":
                deps = [l.split("==")[0].split(">=")[0].strip() for l in txt.splitlines() if l.strip() and not l.startswith("#")]
            elif name == "pyproject.toml":
                deps = re.findall(r"^\s*[\"']([A-Za-z0-9_\-\[\]]+)", txt, re.M)
            res["build"].append({"file": r, "deps": deps[:cap]})
            continue
        if re.match(r"(docker-)?compose[\w.\-]*\.ya?ml$", low):
            res["runtime"]["compose"].append({"file": r, "services": parse_compose(p)})
            continue
        if low.startswith("dockerfile"):
            txt = p.read_text(encoding="utf-8", errors="ignore")
            res["runtime"]["dockerfiles"].append({
                "file": r,
                "from": re.findall(r"^FROM\s+(\S+)", txt, re.M | re.I),
                "expose": re.findall(r"^EXPOSE\s+(.+)", txt, re.M | re.I),
                "cmd": (re.findall(r"^(?:CMD|ENTRYPOINT)\s+(.+)", txt, re.M | re.I) or [None])[-1],
            })
            continue
        if ".github/workflows" in r:
            res["runtime"]["ci"].append(r)
            continue
        if p.suffix in (".yaml", ".yml") and "kind:" in (txt := p.read_text(encoding="utf-8", errors="ignore")[:20000]) \
                and "apiVersion:" in txt:
            for kind, nm in re.findall(r"kind:\s*(\w+)[\s\S]{0,200}?name:\s*([\w\-]+)", txt):
                res["runtime"]["k8s"].append({"file": r, "kind": kind, "name": nm})
            continue
        if CONF_NAMES.match(name):
            for k, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                s = line.strip()
                if s and not s.startswith("#") and CONF_KEYS.search(s):
                    s = re.sub(r"(password|secret|token|key)\s*([:=])\s*\S+", r"\1\2 ***", s, flags=re.I)
                    res["config_hints"].append(f"{r}:{k}: {s[:160]}")
            continue
        if p.suffix not in CODE_EXT:
            continue
        res["languages"][p.suffix] += 1
        try:
            lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        class_prefix = ""
        for k, line in enumerate(lines, 1):
            loc = f"{r}:{k}"
            s = line.strip()
            if not s or s.startswith(("//", "#", "*", "/*")) and "@" not in s:
                continue
            m = PATTERNS["spring_mapping"].search(s)
            if m:
                # 클래스 레벨 @RequestMapping 은 접두사로 기억
                nxt = " ".join(lines[k:k + 3])
                if m.group(1) == "Request" and re.search(r"\bclass\b", nxt):
                    class_prefix = m.group(2)
                    res["entrypoints"]["http"].append(f"{loc}  [class prefix] {m.group(2)}")
                else:
                    verb = m.group(1).upper() if m.group(1) != "Request" else "ANY"
                    res["entrypoints"]["http"].append(f"{loc}  {verb} {class_prefix}{m.group(2)}")
                continue
            m = PATTERNS["spring_mapping_bare"].search(s)
            if m:
                res["entrypoints"]["http"].append(f"{loc}  {m.group(1).upper()} {class_prefix or '/'}")
                continue
            for key, bucket in (("kafka_listener", "consumer"), ("rabbit_listener", "consumer"), ("scheduled", "scheduled")):
                m = PATTERNS[key].search(s)
                if m:
                    res["entrypoints"][bucket].append(f"{loc}  @{key}: {m.group(1)[:100]}")
            m = PATTERNS["fastapi_route"].search(s)
            if m and m.group(1) not in ("self", "requests", "httpx", "client", "session"):
                res["entrypoints"]["http"].append(f"{loc}  {m.group(2).upper()} {m.group(3)}  ({m.group(1)})")
            for key in ("fastapi_router_prefix", "include_router"):
                m = PATTERNS[key].search(s)
                if m and "prefix" in m.group(1):
                    res["entrypoints"]["http"].append(f"{loc}  [router] {m.group(1)[:100]}")
            m = PATTERNS["flask_route"].search(s)
            if m:
                res["entrypoints"]["http"].append(f"{loc}  ROUTE {m.group(2)}")
            m = PATTERNS["express_route"].search(s)
            if m and p.suffix in (".js", ".ts"):
                res["entrypoints"]["http"].append(f"{loc}  {m.group(2).upper()} {m.group(3)}")
            if PATTERNS["celery_task"].search(s) and p.suffix == ".py":
                res["entrypoints"]["worker"].append(f"{loc}  celery task")
            if PATTERNS["spring_controller"].search(s):
                res["entrypoints"]["controllers"].append(loc)
                class_prefix = ""
            for key, bucket in (("feign", "http_out"), ("kafka_send", "producer"), ("http_client_java", "http_out"),
                                ("py_http", "http_out"), ("js_http", "http_out"),
                                ("object_storage", "storage"), ("messaging", "messaging"), ("jpa_repo", "persistence"), ("mybatis_mapper", "persistence"),
                                ("subprocess", "process"), ("llm_sdk", "llm"), ("sse_ws", "streaming")):
                m = PATTERNS[key].search(s)
                if m and len(res["integrations"][bucket]) < cap:
                    res["integrations"][bucket].append(f"{loc}  {s[:120]}")
            for u in PATTERNS["url"].findall(s):
                if not URL_NOISE.search(u):
                    res["urls"][u.rstrip(".,);\"'")] += 1

    for k in list(res["entrypoints"]):
        res["entrypoints"][k] = res["entrypoints"][k][:cap * 2]
    res["entrypoints"] = dict(res["entrypoints"])
    res["integrations"] = dict(res["integrations"])
    res["config_hints"] = res["config_hints"][:cap * 2]
    res["urls"] = dict(res["urls"].most_common(cap))
    res["languages"] = dict(res["languages"].most_common())
    res["git"] = git_summary(root)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", type=Path)
    ap.add_argument("-o", "--out", type=Path)
    ap.add_argument("--max", type=int, default=60, help="항목별 최대 개수")
    a = ap.parse_args()
    data = scan(a.repo.resolve(), a.max)
    txt = json.dumps(data, ensure_ascii=False, indent=1)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(txt, encoding="utf-8")
        ep = sum(len(v) for v in data["entrypoints"].values())
        print(f"스캔 완료: {a.out}  (진입점 {ep}개, 연동 {sum(len(v) for v in data['integrations'].values())}개, "
              f"compose 서비스 {sum(len(c['services']) for c in data['runtime']['compose'])}개)")
    else:
        print(txt)


if __name__ == "__main__":
    main()
