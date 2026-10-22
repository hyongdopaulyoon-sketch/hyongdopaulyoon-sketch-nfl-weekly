"""graphify 코퍼스 사본 만들기(2026-10-21 Paul 「NFL 도 NBA·MLB 처럼 graphify 그래프」 · 복기/개선/수정 세션 상의).
  python scripts/build_graph_src.py          → graphify_src/ (gitignore) 를 새로 만든다
넣는 것: scripts/*.py · scripts/*.md(pending_rules 등) · README · 발행 스킬(계정·로컬 사본) · 복붙용 지침 ·
        주차별 발행문 전부 · 주차별 전달문 머리(경기 절 앞 — 규칙·지시 부분만) · 최근 3주 DIGEST 머리(N0~N12 · 경기 절 앞).
빼는 것: csv·json·xlsx·html(보드)·캐시 · check_nfl 출력 · 다이제스트/전달문의 경기 절(값 로그 — 노드만 늘어난다).
그래프 구축: `/graphify graphify_src` → graphify-out/graph.json·GRAPH_REPORT.md 커밋(graph.html 은 로컬)."""
import glob, os, re, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "graphify_src")
GAME = re.compile(r"(?m)^## [A-Z]{2,3}@[A-Z]{2,3}\b")


def head(path):
    t = open(path, encoding="utf-8").read()
    m = GAME.search(t)
    return t[:m.start()] if m else t


def put(rel, text):
    p = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w", encoding="utf-8").write(text)


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    n = 0
    for p in sorted(glob.glob(os.path.join(ROOT, "scripts", "*.py")) + glob.glob(os.path.join(ROOT, "scripts", "*.md"))):
        if os.path.basename(p) == "build_graph_src.py":
            continue
        put(os.path.join("scripts", os.path.basename(p)), open(p, encoding="utf-8").read()); n += 1
    for rel in ("README.md",):
        p = os.path.join(ROOT, rel)
        if os.path.exists(p):
            put(rel, open(p, encoding="utf-8").read()); n += 1
    for p in glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md")):
        put(os.path.join("skills", os.path.basename(os.path.dirname(p)) + "_SKILL.md"), open(p, encoding="utf-8").read()); n += 1
    for p in glob.glob(os.path.join(ROOT, "복붙용*.md")):
        put(os.path.basename(p), open(p, encoding="utf-8").read()); n += 1
    weeks = sorted(d for d in glob.glob(os.path.join(ROOT, "data", "2026-w*")) if os.path.isdir(d))
    for d in weeks:
        wk = os.path.basename(d)
        for p in sorted(glob.glob(os.path.join(d, "발행-*.md"))):
            put(os.path.join("weeks", wk, os.path.basename(p)), open(p, encoding="utf-8").read()); n += 1
        for p in sorted(glob.glob(os.path.join(d, "전달문-*.md"))):
            put(os.path.join("weeks", wk, os.path.basename(p)), head(p)); n += 1
    for d in [w for w in weeks if os.path.exists(os.path.join(w, "DIGEST.md"))][-3:]:
        put(os.path.join("digest_heads", os.path.basename(d) + "_DIGEST_head.md"), head(os.path.join(d, "DIGEST.md"))); n += 1
    size = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(OUT) for f in fs)
    print(f"graphify_src: {n} files · {size / 1e3:.0f}KB")


if __name__ == "__main__":
    main()
