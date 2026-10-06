# =============================================================
# ranking.py — 補助金逆引きアプリ MVP
# 役割: 店主の口語（translator.py の出力）を、DB内の補助金候補の
#       順位付けに変換する「並べ替え係」。
# 呼び出し経路: app.py → translator.translate() → search_subsidies(...)
# 設計方針: jGrants API は sort パラメータで並べるだけで、スコアリングは行わない。
# =============================================================

import re
from datetime import date

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# ── 定数（MVPでチューニングするのはこの7つだけ） ──────────────

# 飲食店オーナーの投資判断に結びつきにくい制度を候補から外すヒント（制度名・目的タグ用）
EXCLUDE_HINTS = [
    "農業", "林業", "水産", "漁業", "畜産", "医療", "介護",
    "福祉", "大学", "研究機関", "自治体", "地方公共団体",
]

# 飲食店に関係する業種コード（jGrants公式20分類のうち）
RESTAURANT_INDUSTRIES = {
    "宿泊業、飲食サービス業",              # ◎ 本命
    "卸売業、小売業",                      # ○ 物販・テイクアウト併設
    "生活関連サービス業、娯楽業",          # ○ 近隣サービス業
    "サービス業（他に分類されないもの）",  # ○ その他サービス
}

# 業種の列挙数がこれ以下なら「専用制度」とみなす（係数は実データで調整）
NARROW_INDUSTRY_MAX = 3

# 飲食関連の可能性が高い語（該当したら順位をわずかに押し上げる）
# ※ 汎用語（DX/IT/設備/デジタル）は全業種の制度にヒットするため入れない
RESTAURANT_HINTS = [
    "飲食", "小規模事業者", "中小企業", "創業", "商店街", "省力化",
]

# 市区町村 → 都道府県（MVPは手動シード。自治体を増やす時はここに追記）
CITY_TO_PREF = {
    "豊島区": "東京都",
    "練馬区": "東京都",
    "杉並区": "東京都",
    "新宿区": "東京都",
}

# スコア係数（説明可能な係数を明示しておく）
TAG_MATCH_BOOST = 1.5      # use_purpose タグが翻訳カテゴリと一致
LITERAL_BOOST = 1.3        # 店主の言葉そのものが制度名・タグに出現
RESTAURANT_BOOST = 1.2     # 飲食関連の可能性ヒントに該当

# 足切りと下限
SCORE_FLOOR = 0.001        # これ以下の類似度は「無関係」とみなす
MIN_SCORE = 10.0           # タグ・キーワードで拾った候補に与える最低スコア

# 利用者が選ぶ業種 → 制度の industry 欄に含まれていてほしい語
# ※ 制度の industry が空のものは除外しない（未取得データの誤爆防止）
INDUSTRY_KEYWORDS = {
    "飲食店": ["飲食", "宿泊", "サービス"],
    "小売店": ["小売", "卸売", "商店"],
}

# 制度名にこれらの語があり、かつ利用者業種と無関係な場合の追加除外ヒント
# （industry未取得でも「建築GX」のような他業種専用制度を弾く）
OFF_TARGET_TITLE_HINTS = ["建築", "建設", "病院", "医療", "農業", "漁業", "林業"]


# ── 検索エンジン（TF-IDF） ──────────────────────────────────

class SearchEngine:
    """日本語を文字N-gramで扱うTF-IDFエンジン。search_subsidies の内部部品。"""

    def __init__(self):
        # 日本語は単語間にスペースが無いため、文字2〜3gramを特徴量にする
        self.vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 3),
            max_features=5000,
            min_df=1,
            max_df=0.95,
            sublinear_tf=True,
        )
        self.tfidf_matrix = None
        self.docs = []

    def build_index(self, docs: list):
        """補助金1件を1文書として索引を構築する"""
        if not docs:
            return
        self.docs = docs
        corpus = []
        for d in docs:
            title = d.get("title") or ""
            tags = d.get("use_purpose") or ""
            # タイトルは3倍、目的タグは2倍の重みを付ける
            corpus.append(" ".join([
                (title + " ") * 3,
                (tags + " ") * 2,
            ]))
        # 文書数が少ない時に max_df=0.95 が "min_df(1) 未満" になって落ちるのを防ぐ
        # （業種フィルタで1件だけ残った場合など）。max_df は「出現文書率の上限」なので
        # 文書数に応じて (n-1)/n まで下げる。
        n = len(corpus)
        if n < 2:
            self.tfidf_matrix = None
            return
        safe_max_df = min(0.95, (n - 1) / n)
        self.vectorizer.set_params(max_df=safe_max_df)
        self.tfidf_matrix = self.vectorizer.fit_transform(corpus)

    def similarity(self, query: str) -> list:
        """クエリとのコサイン類似度を補助金1件ごとに返す"""
        if self.tfidf_matrix is None or not query.strip():
            return [0.0] * len(self.docs)
        query_vec = self.vectorizer.transform([query])
        return [float(x) for x in cosine_similarity(query_vec, self.tfidf_matrix)[0]]


# ── 絞り込みヘルパー ────────────────────────────────────────

def _split_regions(subsidy_region: str) -> list:
    """'東京都/大阪府' '東京都、大阪府' などを分割する"""
    text = (subsidy_region or "").replace("、", "/").replace(",", "/")
    return [r.strip() for r in text.split("/") if r.strip()]


def region_matches(subsidy_region: str, target_area: str) -> bool:
    """地域の包含判定。豊島区を指定したら 豊島区＋東京都＋全国 を通す。"""
    if not target_area:
        return True
    regions = _split_regions(subsidy_region)
    if not regions or any("全国" in r for r in regions):
        return True
    if any(target_area in r for r in regions):
        return True
    for city, pref in CITY_TO_PREF.items():
        if city in target_area:
            return any(pref in r for r in regions)
    return False


def is_narrow_offtarget(subsidy: dict) -> bool:
    """業種数が少ない専用制度で、飲食系を含まない → 除外する。

    - industry 未取得（空）: 除外しない（enricher未処理の誤爆防止・安全側）
    - 業種を多数列挙（全業種OK型）: 除外しない（事業再構築等の大手を残す）
    - 少数業種かつ飲食系なし: 除外する（農家認証・水産認証などの専用制度）
    """
    raw = (subsidy.get("industry") or "").strip()
    if not raw:
        return False
    inds = [x.strip() for x in raw.split(" / ") if x.strip()]
    if len(inds) > NARROW_INDUSTRY_MAX:
        return False
    return not any(i in RESTAURANT_INDUSTRIES for i in inds)


def _is_excluded(subsidy: dict) -> bool:
    """飲食店オーナーには無関係な制度を弾く（制度名・目的タグ＋業種）"""
    haystack = f"{subsidy.get('title') or ''} {subsidy.get('use_purpose') or ''}"
    if any(h in haystack for h in EXCLUDE_HINTS):
        return True
    # 業種は「部分一致除外」ではなく「少数専用制度の毒見」で判定（旧EXCLUDE_INDUSTRIES廃止）
    if is_narrow_offtarget(subsidy):
        return True
    return False



def industry_matches(subsidy: dict, industry_type: str) -> bool:
    """利用者業種との整合判定。制度の industry が空なら通す（誤爆防止）。
    industry未取得でも、制度名が明らかに他業種専用なら落とす。"""
    if not industry_type:
        return True
    si = (subsidy.get("industry") or "").strip()
    title = subsidy.get("title") or ""
    if si:
        kws = INDUSTRY_KEYWORDS.get(industry_type, [industry_type])
        return any(k in si for k in kws)
    # industry 未取得の場合: タイトルが他業種専用っぽいなら落とす
    return not any(h in title for h in OFF_TARGET_TITLE_HINTS)


def employees_ok(subsidy: dict, employees: int) -> bool:
    """従業員数要件の判定。
    '従業員数の制約なし' / 空 / パース不能 は通す（安全側）。
    '20名以下' → 利用者が20人以下なら通す、'300名以下' も同様。"""
    if employees is None:
        return True
    text = (subsidy.get("target_employees") or "").strip()
    if not text or "制約なし" in text:
        return True
    m = re.search(r"(\d[\d,]*)\s*(?:名|人)", text)
    if not m:
        return True
    limit = int(m.group(1).replace(",", ""))
    if "以下" in text:
        return employees <= limit
    if "以上" in text:
        return employees >= limit
    return True


def _tags_of(subsidy: dict) -> set:
    """use_purpose を ' / ' 区切りのタグ集合に変換する"""
    raw = subsidy.get("use_purpose") or ""
    return set(t.strip() for t in raw.replace("/", "／").split("／") if t.strip())


# ── 本体 ────────────────────────────────────────────────────

def search_subsidies(subsidies: list, translated: dict,
                     target_area: str = "", sort_by: str = "amount",
                     top_n: int = 5,
                     industry_type: str = "", employees: int = None) -> list:
    """翻訳結果から補助金候補をランク付けして返す。

    subsidies  : database.get_all_subsidies() の戻り値
    translated : translator.translate() の戻り値 {"categories":[...], "matches":{...}}
    target_area: '豊島区' など。空なら地域絞り込みなし
    sort_by    : "amount"（上限額が大きい順） / "deadline"（締切が近い順） / "relevance"（意味スコア順）
    """
    # クエリは「カテゴリ名＋ヒット語」の両方で作る
    query_parts = list(translated.get("categories") or [])
    query_words = []
    for words in (translated.get("matches") or {}).values():
        query_words.extend(words)
    query_parts.extend(query_words)
    query = " ".join(query_parts)
    if not query.strip():
        return []

    today = date.today().isoformat()

    # 1) 締切切れを除外 → 2) 無関係業種を除外 → 3) 地域を包含判定
    #    → 4) 利用者業種との整合 → 5) 従業員数要件
    active = [
        s for s in subsidies
        if (not s.get("deadline") or s["deadline"] >= today)
        and not _is_excluded(s)
        and region_matches(s.get("region") or "", target_area)
        and industry_matches(s, industry_type)
        and employees_ok(s, employees)
    ]
    if not active:
        return []

    # 4) TF-IDF で意味的な近さを測る
    engine = SearchEngine()
    engine.build_index(active)
    scores = engine.similarity(query)

    # 5) 係数を掛けて説明可能なスコアにする
    categories = set(translated.get("categories") or [])
    results = []
    for subsidy, base_score in zip(active, scores):
        tags = _tags_of(subsidy)
        tag_match = bool(categories & tags)

        haystack = f"{subsidy.get('title') or ''} {subsidy.get('use_purpose') or ''}"
        literal_hit = any(w and w in haystack for w in query_words)

        # 採用条件: 意味的に近い か 目的タグ一致 か キーワード一致
        if base_score <= SCORE_FLOOR and not tag_match and not literal_hit:
            continue

        score = max(base_score * 100, MIN_SCORE)
        reasons = []
        boosts = {}
        if tag_match:
            score *= TAG_MATCH_BOOST
            reasons.append("目的タグ一致")
            boosts["目的タグ一致"] = TAG_MATCH_BOOST
        if literal_hit:
            score *= LITERAL_BOOST
            reasons.append("キーワード一致")
            boosts["キーワード一致"] = LITERAL_BOOST
        if any(h in (subsidy.get("title") or "") for h in RESTAURANT_HINTS):
            score *= RESTAURANT_BOOST
            reasons.append("飲食関連の可能性")
            boosts["飲食関連の可能性"] = RESTAURANT_BOOST
        boost_total = 1.0
        for v in boosts.values():
            boost_total *= v

        results.append({
            "id": subsidy.get("id"),
            "title": subsidy.get("title"),
            "region": subsidy.get("region"),
            "max_amount": subsidy.get("max_amount"),
            "deadline": subsidy.get("deadline"),
            "use_purpose": subsidy.get("use_purpose"),
            "source_url": subsidy.get("source_url"),
            "relevance_score": round(score, 1),
            "base_score": round(max(base_score * 100, MIN_SCORE), 1),
            "boosts": boosts,
            "boost_total": round(boost_total, 2),
            "bonus_note": "、".join(reasons),
            "_raw": subsidy,
        })

    if not results:
        return []

    # 6) 並べ替え（3つの軸を明示）
    if sort_by == "deadline":
        results.sort(key=lambda r: (r.get("deadline") or "9999-12-31"))
    elif sort_by == "relevance":
        results.sort(key=lambda r: r["relevance_score"], reverse=True)
    else:  # amount
        results.sort(key=lambda r: (r.get("max_amount") or 0), reverse=True)

    return results[:top_n]
