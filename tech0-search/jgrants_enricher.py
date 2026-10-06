# =============================================================
# jgrants_enricher.py — 募集中の制度だけ詳細APIで業種を補強する
# 実行: python jgrants_enricher.py
#
# なぜ必要か:
#   一覧APIには industry（業種）が無い。業種が無いと
#   「建築GX・DX推進事業」のような他業種の制度が
#   飲食店への提案に紛れ込む...。
#
# 動作:
#   1) DBから 募集中 かつ source="jgrants" かつ industry未取得 の制度を拾う
#   2) 1件ずつ詳細APIを GET（429レート制限対策で1秒間隔）
#   3) industry / subsidy_rate / description / 公式URL を UPDATE（UPSERT）
#
# 所要時間の目安: 募集中約290件 × 1秒 = 約5分
# =============================================================

import re
import time
from datetime import date, datetime

import requests

# データベース操作用関数のインポート
from database import get_all_subsidies, insert_subsidy

# 詳細情報取得用の API エンドポイント URLテンプレート
DETAIL_API = "https://api.jgrants-portal.go.jp/exp/v1/public/subsidies/id/{}"

# APIサーバーへの過度な負荷（HTTP 429 Too Many Requests）を避けるための待機時間（秒）
SLEEP_SEC = 1.0  # 429レート制限を避けるため1秒あける（実測で調整）


def clean_html(html: str) -> str:
    """詳細文のHTMLタグを落としてプレーンテキストにする

    Args:
        html (str): APIから取得したHTMLタグ付きの詳細説明テキスト

    Returns:
        str: HTMLタグが除去され、連続する空白が整形されたプレーンテキスト
    """
    # 1. `<...>` 形式のHTMLタグをすべて半角スペース1個に置換
    text = re.sub(r"<[^>]+>", " ", html or "")
    # 2. 連続する改行や空白文字（\s+）をスペース1個にまとめて前後の余白を除去
    return re.sub(r"\s+", " ", text).strip()


def fetch_detail(subsidy_id: str) -> dict:
    """詳細APIから1件分の業種・補助率・詳細文を取る。

    Args:
        subsidy_id (str): 補助金制度の固有ID (source_id)

    Returns:
        dict: 制度の詳細情報オブジェクト。
              `result` が空リスト（公開終了・削除済みの制度）なら空の辞書 `{}` を返す。
    """
    # 指定された subsidy_id をURLに埋め込んでGETリクエストを発行
    resp = requests.get(DETAIL_API.format(subsidy_id), timeout=30)
    
    # HTTPステータスコードがエラー（4xx, 5xx）の場合は例外を発生させる
    resp.raise_for_status()
    
    # APIレスポンス構造: {"result": [{詳細データ}]}
    result = resp.json().get("result") or []
    
    # データが存在すれば先頭要素(dict)を返し、公開終了等で空配列の場合は空辞書 {} を返却
    return result[0] if result else {}


def run():
    """DB内の「募集中」かつ「業種未設定」なjGrantsデータに対し、

    詳細APIを呼び出して業種・補助率・詳細説明・公式URLを自動補強するメイン処理。
    """
    # 今日の日付文字列（YYYY-MM-DD）を取得して締切日判定用に使用
    today = date.today().isoformat()
    
    # DBに登録されている全補助金データを取得
    all_rows = get_all_subsidies()

    # 詳細情報を補強すべき対象データをフィルタリング
    # 条件:
    #   1. データ取得元が "jgrants" であること
    #   2. 締切日（deadline）が今日以降、または未設定（無期限・随時募集）であること
    #   3. 業種（industry）が未設定（空文字または空白のみ）であること
    targets = [
        s for s in all_rows
        if s.get("source") == "jgrants"
        and (not s.get("deadline") or s["deadline"] >= today)
        and not (s.get("industry") or "").strip()
    ]
    print(f"業種の補強対象: {len(targets)} 件（募集中・未取得のみ）")

    # 処理件数のカウンター初期化
    updated = skipped = failed = 0
    
    # 対象データを1件ずつループ処理（インデックスを1始まりで取得）
    for i, s in enumerate(targets, 1):
        sid = s.get("source_id")
        try:
            # 詳細APIを発行して1件分の詳細データを取得
            detail = fetch_detail(sid)
            
            if not detail:
                # APIに詳細が存在しない（公開終了・削除済み）→ スキップ
                skipped += 1
                print(f"  - {sid}: 詳細データなし（公開終了の可能性）→ スキップ")
            else:
                # APIから取得できた値で既存辞書オブジェクト `s` の各フィールドを上書き・補強
                s["industry"] = detail.get("industry") or ""
                s["subsidy_rate"] = detail.get("subsidy_rate") or s.get("subsidy_rate", "")
                s["description"] = clean_html(detail.get("detail", ""))
                
                # 詳細画面URLを取得できた場合は正として更新
                official = detail.get("front_subsidy_detail_page_url")
                if official:
                    s["source_url"] = official  # 公式が返す制度ページURLを正とする
                    
                # 最終更新日時を現在日時に更新
                s["fetched_at"] = datetime.now().isoformat()
                
                # DBへ更新登録（`UNIQUE(source, source_id)` の制約に基づきUPSERTを実行）
                insert_subsidy(s)  # UNIQUE(source, source_id) でUPSERT
                updated += 1

        except requests.RequestException as e:
            # ネットワーク接続エラーやタイムアウトなどの例外処理
            failed += 1
            print(f"  ⚠️ {sid}: 通信エラー（{e}）→ スキップ")
        except (ValueError, KeyError, TypeError) as e:
            # パース失敗やキー不整合などのデータ型エラーの例外処理
            failed += 1
            print(f"  ⚠️ {sid}: データ形式エラー（{e}）→ スキップ")
            
        # 50件処理ごとに中間進捗ログを標準出力に表示
        if i % 50 == 0:
            print(f"  ... {i}/{len(targets)} 件処理済み（更新{updated} / スキップ{skipped} / 失敗{failed}）")
            
        # API側のレート制限（HTTP 429）を回避するため指定秒数スリープ
        time.sleep(SLEEP_SEC)

    # 最終結果のサマリー出力
    print(f"完了: 更新 {updated} 件 / 詳細なしスキップ {skipped} 件 / 失敗 {failed} 件")


if __name__ == "__main__":
    # スクリプト直接実行時に処理を開始
    run()