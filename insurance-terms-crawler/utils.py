# -*- coding: utf-8 -*-
"""문서종류 판별 · 파일명 정리 · 인코딩 · URL 헬퍼."""
import hashlib
import re
from urllib.parse import unquote, urljoin

# 수집 범위 = '보험약관' 전문만. 아래 키워드가 들어가면 약관이 아니라고 보고 제외.
TERMS_KW = "약관"
EXCLUDE_KW = (
    "사업방법서", "방법서", "상품요약서", "상품설명서", "가입설명서",
    "요약서", "설명서", "안내서", "제안서", "신청서", "청구서",
    "리플릿", "팜플렛", "공시이율", "운용설명서",
)


def is_terms_doc(*texts) -> bool:
    """주어진 텍스트(컬럼헤더/링크텍스트/파일명 등) 조합이 '보험약관'을 가리키면 True."""
    blob = " ".join(t for t in texts if t)
    if TERMS_KW not in blob:
        return False
    return not any(k in blob for k in EXCLUDE_KW)


def sanitize_filename(name: str, maxlen: int = 160) -> str:
    if not name:
        return "unnamed"
    name = unquote(name)
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", name)
    name = re.sub(r"\s+", " ", name).strip().strip(". ")
    return (name[:maxlen] or "unnamed")


def short_hash(s: str, n: int = 8) -> str:
    return hashlib.sha1((s or "").encode("utf-8", "ignore")).hexdigest()[:n]


def recover_header_text(s: str) -> str:
    """requests 는 HTTP 헤더를 latin-1 로 디코딩한다. 원본이 UTF-8/EUC-KR(또는 이중 인코딩)이면 복구.

    한국 보험사 서버는 파일명을 UTF-8 로 두 번 인코딩해 보내는 경우가 있어(mojibake²),
    더 이상 latin-1 로 인코딩되지 않을 때(=진짜 한글이 나타날 때)까지 반복 복구한다.
    """
    if not s:
        return s
    cur = s
    for _ in range(3):  # 단일/이중 인코딩까지 커버
        try:
            raw = cur.encode("latin-1")
        except UnicodeEncodeError:
            break  # 이미 비-latin1(한글 등) 포함 → 복구 완료
        try:
            dec = raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return raw.decode("euc-kr")
            except UnicodeDecodeError:
                break
        if dec == cur:
            break  # 고정점(ASCII 등) → 종료
        cur = dec
    return cur


def cd_filename(header: str):
    """Content-Disposition 헤더에서 파일명 추출(RFC5987 filename* 우선).

    주의: 한국 보험사 서버는 filename=""한글이름.pdf"" (이중 따옴표) +
    UTF-8 바이트를 latin-1 헤더로 흘려보내는 경우가 흔하다 → 따옴표 정리 + 인코딩 복구.
    """
    if not header:
        return None
    m = re.search(r"filename\*\s*=\s*[^']*''([^;]+)", header, re.I)
    if m:
        return recover_header_text(unquote(m.group(1).strip().strip('"')))
    m = re.search(r'filename\s*=\s*"*([^";]+)', header, re.I)
    if m:
        return recover_header_text(unquote(m.group(1).strip()).strip('"').strip())
    return None


def decode_bytes(b: bytes) -> str:
    for enc in ("utf-8", "euc-kr", "cp949"):
        try:
            return b.decode(enc)
        except Exception:
            continue
    return b.decode("utf-8", "ignore")


def abs_url(href: str, base: str) -> str:
    if not href:
        return ""
    href = href.strip()
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("http"):
        return href
    return urljoin(base.rstrip("/") + "/", href.lstrip("/"))


# ----- Playwright 렌더 후 PDF 링크 일괄 추출용 JS -----
# 각 링크에 대해 href/onclick + 같은 행의 컬럼헤더/상품명까지 같이 뽑아 약관 컬럼만 필터 가능하게 함.
SWEEP_JS = r"""
(tokens) => {
  function headerFor(cell){
    const tr = cell.closest('tr'); if(!tr) return '';
    const table = tr.closest('table'); if(!table) return '';
    const idx = Array.prototype.indexOf.call(tr.children, cell);
    let head = table.querySelector('thead tr');
    if(!head){ const rows = table.querySelectorAll('tr'); head = rows.length?rows[0]:null; }
    if(head && head.children[idx]) return (head.children[idx].textContent||'').trim();
    return '';
  }
  const out = [];
  document.querySelectorAll('a[href],[onclick],button[data-href]').forEach(el => {
    const href = el.getAttribute('href') || el.getAttribute('data-href') || '';
    const oc = el.getAttribute('onclick') || '';
    const blob = href + ' ' + oc;
    if(!tokens.some(t => blob.indexOf(t) >= 0)) return;
    const cell = el.closest('td') || el;
    const tr = el.closest('tr');
    out.push({
      href: href,
      onclick: oc,
      text: (el.textContent || '').trim(),
      colHeader: cell ? headerFor(cell) : '',
      rowName: tr && tr.querySelector('td') ? (tr.querySelector('td').textContent || '').trim() : '',
      aria: el.getAttribute('aria-label') || el.getAttribute('title') || ''
    });
  });
  return out;
}
"""
