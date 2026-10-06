# ==============================================================================
# jGrants API 補助金データ取得・DB登録スクリプト
#
# 【概要】
#   デジタル庁が提供する jGrants (補助金申請システム) の公開APIから
#   補助金・助成金の公募情報を自動取得し、ローカルデータベースへ登録。
#
# 【処理フロー】
#   1. TRANSLATION_DICT から15種類の目的・カテゴリーを取得
#   2. カテゴリーごとに API へ GET リクエストを発行
#   3. 得られたレスポンスをメモリ上で結合し、制度ID(id)をキーにして重複を排除
#   4. 複数カテゴリーに該当する制度には、タグ（use_purpose）を統合
#   5. DBスキーマ用に整形（マッピング）後、データベースへ一括・更新登録
#
# 実行方法:
#   python jgrants_fetcher.py
# ==============================================================================

import requests
from datetime import datetime

# DB操作モジュールとカテゴリー定義辞書をインポート
from database import init_db, insert_subsidy
from translator import TRANSLATION_DICT   # 15カテゴリー一覧は辞書のキーを借用

# jGrants API v1 公開エンドポイント（補助金一覧取得）
API_URL = "https://api.jgrants-portal.go.jp/exp/v1/public/subsidies"

# APIリクエスト時に送信するデフォルトのクエリパラメータ設定
REQUEST_BODY = {
    "keyword": "事業",        # 幅広く拾うための汎用語（2文字以上必須）
    "sort": "created_date",   # 並び順の基準（作成日時）
    "order": "DESC",          # 降順（新しい順）
    "acceptance": "0",        # 受付ステータス ("0": 期間を問わず全件, "1": 募集中のみ)
}


def fetch_subsidies() -> list:
    """jGrants API から制度一覧を取得して、生のリストを返す（GET方式）

    グローバル変数 `REQUEST_BODY` をクエリパラメータとして使用し、
    jGrants APIへリクエストを送信します。

    Returns:
        list: APIから返却された補助金データ（辞書）のリスト。取得失敗時は例外を送出。
    """
    # URLクエリパラメータとして REQUEST_BODY を付与してGETリクエスト送信
    resp = requests.get(API_URL, params=REQUEST_BODY, timeout=60)
    
    # ステータスコードが 200 OK 以外の場合は HTTPError 例外を発生させる
    resp.raise_for_status()
    
    data = resp.json()
    
    # APIレスポンス構造: {"result": [{補助金1}, {補助金2}, ...]}
    return data.get("result", [])   # 制度リストは result キーの中に格納されている


def to_subsidy(item: dict) -> dict:
    """APIの1件分の raw データを、subsidiesテーブルのデータ構造に変換・整形する（マッピング）

    Args:
        item (dict): jGrants APIから取得した生の補助金1件分のデータ辞書

    Returns:
        dict: DB登録用（subsidiesテーブルの各カラム）に対応した辞書データ
    """

    # ISO8601形式の日時文字列（例: "2026-10-16T08:00:00Z"）から年月日（"YYYY-MM-DD"）のみ抽出
    # Noneが返る可能性に備えて `or ""` で空文字にフォールバック処理
    start = (item.get("acceptance_start_datetime") or "")[:10]
    end = (item.get("acceptance_end_datetime") or "")[:10]

    # jGrants側の固有識別子（ID）
    subsidy_id = item.get("id", "")

    # DBのテーブル定義に合わせた辞書オブジェクトを構築して返却
    return {
        "title": item.get("title", ""),
        "description": "",                                                     # 詳細説明（API一覧からは取得できないため空文字）
        "max_amount": item.get("subsidy_max_limit") or 0,                       # 上限金額（Noneの場合は0に置換）
        "subsidy_rate": "",                                                    # 補助率（必要に応じて拡張用）
        "start_date": start,                                                   # 受付開始日 (YYYY-MM-DD)
        "deadline": end,                                                       # 受付終了日/締切 (YYYY-MM-DD)
        "region": item.get("target_area_search", ""),                          # 対象地域
        "industry": "",                                                        # 該当業種（拡張用）
        "use_purpose": "",                                                     # 利用目的/カテゴリー（run関数内で後から設定）
        "target_employees": item.get("target_number_of_employees", ""),        # 対象従業員数
        "source": "jgrants",                                                   # データ取得元識別子
        "source_id": subsidy_id,                                               # 取得元でのID
        "source_url": f"https://www.jgrants-portal.go.jp/subsidy/{subsidy_id}",# jGrantsポータルの詳細画面URL
        "fetched_at": datetime.now().isoformat(),                              # データ取得日時（ISOフォーマット）
    }


def run():
    """メイン実行処理

    15個の目的カテゴリーごとにAPI検索を実行し、重複する補助金データを一元化。
    複数カテゴリーに合致した補助金にはタグを結合付与した上でデータベースに登録します。
    """
    # データベースとテーブルの初期化（未作成の場合に作成）
    init_db()

    # 取得データを一元管理・重複除去するための辞書
    # 構造: { subsidy_id: { API生データ... , "_purposes": set("設備投資", "IT化", ...) } }
    collected = {}

    # 1. 15カテゴリー別にループして全件取得を実施
    for category in TRANSLATION_DICT.keys():
        # クエリパラメータに目的カテゴリーをセットして絞り込み
        REQUEST_BODY["use_purpose"] = category     # 絞り込み条件を差し替え
        
        try:
            items = fetch_subsidies()
        except requests.RequestException as e:
            # ネットワークエラーやタイムアウトが発生しても全体を止めず、エラーを表示して次へ
            print(f"⚠️️ {category}: 取得失敗（{e}）→ このカテゴリーはスキップ")
            continue
            
        print(f"{category}: {len(items)} 件")

        # 2. 取得したアイテムの重複をID単位でチェック・結合
        for item in items:
            sid = item.get("id")
            if not sid:
                continue   # IDが存在しない不正データは除外
                
            # 初めて登場した制度IDの場合は保存用の枠組みを作成
            if sid not in collected:
                collected[sid] = item
                collected[sid]["_purposes"] = set()    # タグ（カテゴリー）を重複なく保持するsetオブジェクト
                
            # 該当するカテゴリー名をタグとしてsetに追加
            collected[sid]["_purposes"].add(category)

    print(f"\nユニーク制度数: {len(collected)} 件")

    # 3. 集約したデータを整形してデータベースへ書き込み
    count = 0
    for sid, item in collected.items():
        # DB登録用の辞書構造に変換
        s = to_subsidy(item)
        
        # 紐付いた複数カテゴリーをアルファベット・五十音順に並べ替え、「 / 」で結合した文字列にする
        # 例: {"設備投資", "省エネ"} → "省エネ / 設備投資"
        s["use_purpose"] = " / ".join(sorted(item["_purposes"]))
        
        # タイトルが空の不完全なデータはノイズ防止のため登録をスキップ
        if not s["title"]:
            continue
            
        # データベースへ登録（既存IDの場合は更新操作）
        insert_subsidy(s)
        count += 1

    print(f"DB登録件数: {count} 件（既存は上書き更新）")


if __name__ == "__main__":
    # スクリプト直接実行時にメイン処理を開始
    run()