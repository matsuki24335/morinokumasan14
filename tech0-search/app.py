# =============================================================
# app.py — 補助金逆引きアプリ MVP（Streamlit画面）
# 実行: streamlit run app.py
#
# これは「営業マンが店先で使う」ための最小画面。
# 入力は4つだけ:
#   1) 店主の言葉   2) 地域   3) 業種   4) 従業員数
# 出力は候補カード（制度名・金額・締切・公式URL）のみ。
#
# データの流れ:
#   入力 → translator.translate()（口語→15分類）
#        → ranking.search_subsidies()（絞り込み＋順位付け）
#        → 画面に表示
# 未実装
#   - 検索ログの保存 …… MVPの価値検証が先。検証後に追加する
# =============================================================

import html
import re

import streamlit as st

from database import init_db, get_all_subsidies
from translator import translate
from ranking import(
    search_subsidies, CITY_TO_PREF, INDUSTRY_KEYWORDS,
    TAG_MATCH_BOOST, LITERAL_BOOST, RESTAURANT_BOOST, MIN_SCORE,
)

# ── 画面の基本設定 ──────────────────────────────────────────
st.set_page_config(page_title="補助金さがし（MVP）", page_icon="◆", layout="centered")

# ── 見た目（最小限のCSSのみ） ───────────────────────────────
st.markdown(
    """
    <style>
      :root{--ink:#14110E;--sub:#5A5347;--gold:#B28B3C;--paper:#FBFAF7;--line:#E8E4D9;}
      .stApp{background:var(--paper);}
      html,body,[class*="css"]{
        font-family:"Helvetica Neue","Hiragino Sans","Noto Sans JP",sans-serif;
        color:var(--ink);
      }
      .block-container{padding-top:2.2rem;padding-bottom:2.5rem;max-width:820px;}

      /* ボタン（黒地に生成り文字。ここ1か所だけ） */
      .stButton>button,[data-testid="stFormSubmitButton"] button,[data-testid="stLinkButton"] a{
        background:var(--ink)!important;border:1px solid var(--ink)!important;
        border-radius:2px!important;padding:.5rem 1.4rem!important;
        font-weight:700!important;font-size:.82rem!important;text-decoration:none!important;
      }
      .stButton>button *,[data-testid="stFormSubmitButton"] button *,[data-testid="stLinkButton"] a *{
        color:#FBF7EC!important;-webkit-text-fill-color:#FBF7EC!important;
      }

      /* 結果カードの枠 */
      [data-testid="stVerticalBlockBorderWrapper"]{
        border:1px solid var(--line)!important;border-radius:4px!important;
        background:#fff!important;padding:1rem 1.15rem!important;
      }

      /* ラジオの選択点＝金 */
      [data-testid="stRadio"] [data-baseweb="radio"] [aria-checked="true"] div{border-color:var(--gold)!important;}
      [data-testid="stRadio"] [data-baseweb="radio"] [aria-checked="true"] div div{background-color:var(--gold)!important;}

      /* フッター */
      .footer{border-top:1px solid var(--line);margin-top:1.8rem;padding-top:.8rem;
              color:var(--sub);font-size:.78rem;line-height:1.6;}
    </style>
    """,
    unsafe_allow_html=True,
)

# ── 見出し ──────────────────────────────────────────────────
st.title("補助金逆引きアプリ")
st.caption("店舗オーナーの言葉から、使えそうな補助金をさがします。")

# ── DB準備（起動時に1回だけ読み込む） ───────────────────────
init_db()


@st.cache_data(show_spinner=False)
def load_subsidies():
    """DBの全制度を読み込む（画面操作中はキャッシュを使う）"""
    return get_all_subsidies()


subsidies = load_subsidies()
st.sidebar.metric("登録制度数", f"{len(subsidies):,} 件")

# ── 入力（地域は CITY_TO_PREF、業種は INDUSTRY_KEYWORDS と自動連動） ──
area_options = [""] + list(CITY_TO_PREF.keys())
industry_options = [""] + list(INDUSTRY_KEYWORDS.keys())

with st.form("search_form", clear_on_submit=False):
    owner_text = st.text_area(
        "店舗オーナーの言葉",
        placeholder="例：インボイス対応でPOSレジを入れたい",
        height=100,
    )

    c1, c2 = st.columns(2)
    with c1:
        target_area = st.selectbox(
            "地域",
            options=area_options,
            format_func=lambda x: "指定しない" if x == "" else x,
        )
    with c2:
        industry_type = st.selectbox(
            "業種",
            options=industry_options,
            format_func=lambda x: "指定しない" if x == "" else x,
        )

    c3, c4 = st.columns([1, 2])
    with c3:
        employees = st.number_input("従業員数（人）", min_value=0, max_value=10000, value=0, step=1)
    with c4:
        sort_label = st.radio(
            "並び順",
            options=["おすすめ順", "上限額が大きい順", "締切が近い順"],
            horizontal=True,
        )

    submitted = st.form_submit_button("さがす")

SORT_KEY = {
    "おすすめ順": "relevance",
    "上限額が大きい順": "amount",
    "締切が近い順": "deadline",
}

# 正しいjGrants制度ページのURLだけをボタンにする（リンク切れ防御）
VALID_URL = re.compile(r"https://www\.jgrants-portal\.go\.jp/subsidy/[A-Za-z0-9]+$")

# ── 検索実行 ────────────────────────────────────────────────
if submitted:
    if not owner_text.strip():
        st.warning("店舗オーナーの言葉を入力してください。")
        st.stop()

    translated = translate(owner_text)
    if not translated["categories"]:
        st.info("言葉を補助金の種類に結びつけられませんでした。「POS」「2号店」など具体的に入力してください。")
        st.stop()

    st.subheader("受け取った目的")
    for cat in translated["categories"]:
        st.write(f"**{cat}**：{'、'.join(translated['matches'][cat])}")

    results = search_subsidies(
        subsidies, translated,
        target_area=target_area,
        sort_by=SORT_KEY[sort_label],
        top_n=5,
        industry_type=industry_type,
        employees=(employees if employees > 0 else None),
    )

    st.subheader("候補（上位5件）")
    if not results:
        st.info("条件に合う募集中の制度がありませんでした。地域や業種を緩めてみてください。")
    else:
        for i, r in enumerate(results, 1):
            amount = r["max_amount"] or 0
            amount_text = f"最大 {amount:,} 円" if amount > 0 else "金額は制度詳細で確認"
            region_text = r["region"] or "全国"
            if len(region_text) > 40:              # 表示のみ短縮（データは不変）
                region_text = region_text[:40] + "…"
            with st.container(border=True):
                st.markdown(f"**{i}. {html.escape(r['title'])}**")
                st.caption(
                    f"{amount_text}　／　締切 {html.escape(r['deadline'] or '要確認')}"
                    f"　／　{html.escape(region_text)}"
                )
                if r["bonus_note"]:
                    st.caption(f"おすすめ理由：{html.escape(r['bonus_note'])}")
                st.caption(
                    f"スコア {r['relevance_score']}"
                    f"（基礎 {r['base_score']} × {r['boost_total']}倍"
                    f"{'：' + '・'.join(f'{k}×{v}' for k, v in r['boosts'].items()) if r['boosts'] else ''}）"
                )
                url = r["source_url"] or ""
                if VALID_URL.match(url):
                    st.link_button("公式サイトで確認", url)
                elif url:
                    st.caption(f"🔗 制度URL（要確認）：{url}")

# ── フッター（常時表示） ────────────────────────────────────
st.markdown(
    '<div class="footer">'
    "出典：jGrantsや地方自治体HPなどから弊社作成<br><br>"
    "<b>スコアの見方</b><br>"
    "スコア（トータル）＝ 基礎スコア × ブースト（係数の掛け合わせ）<br>"
    f"・基礎スコア：制度名・目的タグと、店舗オーナーの言葉の文字の近さ（最低{MIN_SCORE:g}点）<br>"
    f"・目的タグ一致（×{TAG_MATCH_BOOST:g}）：制度の目的が、受け取った目的と一致<br>"
    f"・キーワード一致（×{LITERAL_BOOST:g}）：店舗オーナーの言葉そのものが制度名・タグに出現<br>"
    f"・飲食関連の可能性（×{RESTAURANT_BOOST:g}）：飲食・中小企業など、飲食店に近い語を含む<br>"
    "※「おすすめ順」のときだけスコア順に並びます。金額順・締切順はスコアと無関係です。<br><br>"
    "※ 締切が来ていないもののみ表示しています。<br><br>"
    "⚠️ 候補は制度名・目的タグからの推定です。対象要件（業種・規模・経費の範囲など）は"
    "必ず公式サイトで確認してください。"
    "</div>",
    unsafe_allow_html=True,
)
