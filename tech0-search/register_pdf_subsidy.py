# =============================================================
# # register_pdf_subsidy.py — 補助金逆引きアプリ MVP
# PDFから読んだ制度を、人が確認してDBへ登録する
# 実行： python register_pdf_subsidy.py
# 使い方： SUBSIDY の中身を、抽出テキストを見ながら書き換えてから実行する
# =============================================================

from database import init_db, insert_subsidy

PDF_NAME = "20260415124004.pdf"
PDF_URL = "https://www.city.toshima.lg.jp/documents/56233/20260415124004.pdf"

# ↓↓↓ 抽出テキスト（data/output/toshima_2026_extracted.txt）を見ながら人が記入する欄 ↓↓↓
SUBSIDY = {
    "title": "豊島区 中小企業支援事業補助金 開業⽀援コース（令和8年度）",
    "description": (
        "創業後に必要な経費の一部を補助。"
        "対象経費：①事業PR ②デジタル環境整備 ③専⾨家活⽤"
        "対象者：区内で3ヶ⽉以上かつ5年未満事業を営んでいる⽅、過去に開業⽀援コースの交付を受けていない⽅"
        "申請前に補助金相談（要予約）が必須。"
    ),
    "max_amount": 200000,          # 「最大20万円」→ 円に直す
    "subsidy_rate": "2/3",
    "start_date": "2026-05-11",    # 令和8年5月11日
    "deadline": "2026-11-27",      # 令和8年11月27日
    "region": "東京都豊島区",
    "industry": "",                # 業種指定なし → 空欄
    "use_purpose": "新たな事業を行いたい",   # 15分類タグは人が選ぶ
    "target_employees": "",

    # ↓ ここから下は出どころ情報（基本このまま）
    "source": "municipal_pdf",
    "source_id": f"{PDF_NAME}#kaigyo",   # 約束事①：ファイル名#識別子
    "source_url": PDF_URL,
}
# ↑↑↑ ここまで ↑↑↑


def main():
    init_db()
    subsidy_id = insert_subsidy(SUBSIDY)
    print(f"登録完了（id={subsidy_id}）: {SUBSIDY['title']}")


if __name__ == "__main__":
    main()
