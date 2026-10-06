# =============================================================
# database.py — 補助金逆引きアプリ MVP（データベース、SQLite3)
# 
# 【概要】
#   補助金ナビ用の SQLite データベース接続管理、テーブル初期化、
#   データ登録（UPSERT）、データ検索・取得関数を提供。
#
# 【保管場所】
#   データファイル: data/subsidy_navi.db
# =============================================================

import sqlite3
from pathlib import Path
from datetime import datetime

# DB ファイルの保存先パス（実行ディレクトリ配下の data/ サブフォルダ内）
DB_PATH =  Path(__file__).resolve().parent / "data" / "subsidy_navi.db"


def get_connection():
    """データベースへの接続（sqlite3.Connection）を取得する

    ・保存先ディレクトリ（data/）が存在しない場合は自動作成します。
    ・クエリ結果のカラム名で値にアクセスできるよう sqlite3.Row を設定します。

    Returns:
        sqlite3.Connection: 初期化済みの SQLite 接続オブジェクト
    """
    # 親ディレクトリ（data/）が存在しない場合に自動生成
    DB_PATH.parent.mkdir(exist_ok=True)
    
    # データベースへ接続（ファイルが存在しない場合は新規作成される）
    conn = sqlite3.connect(str(DB_PATH))
    
    # クエリの返り値を `row['title']` や `dict(row)` のように扱えるよう設定
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """schema.sql を読み込んでデータベース・テーブル群を初期化する

    ※ schema.sql 内の DDL (CREATE TABLE IF NOT EXISTS など) を一括実行します。
    """
    conn = get_connection()
    
    # schema.sql ファイルを読み込んで全ステートメントを実行
    SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
        
    conn.commit()
    conn.close()


def insert_subsidy(s: dict) -> int:
    """補助金データを1件登録または更新する（UPSERT処理）

    `UNIQUE(source, source_id)` のユニーク制約に基づき、
    ・未登録の場合: 新規挿入 (INSERT)
    ・既登録の場合: 既存レコードを最新データで上書き更新 (UPDATE)
    を行います。

    Args:
        s (dict): 登録・更新対象の補助金データ辞書

    Returns:
        int: 直近で挿入・操作された行の ID (lastrowid)
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # SQLite 3.24.0 以降でサポートされる UPSERT (ON CONFLICT) 構文を使用
    cursor.execute("""
        INSERT INTO subsidies
            (title, description, max_amount, subsidy_rate,
             start_date, deadline,
             region, industry, use_purpose, target_employees,
             source, source_id, source_url, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (source, source_id)
        DO UPDATE SET
            title        = excluded.title,
            description = excluded.description,
            max_amount  = excluded.max_amount,
            subsidy_rate = excluded.subsidy_rate,
            start_date  = excluded.start_date,
            deadline    = excluded.deadline,
            region      = excluded.region,
            industry    = excluded.industry,
            use_purpose = excluded.use_purpose,
            target_employees = excluded.target_employees,
            source_url  = excluded.source_url,
            fetched_at  = excluded.fetched_at,
            updated_at  = CURRENT_TIMESTAMP
    """, (
        s["title"],
        s.get("description", ""),
        s.get("max_amount", 0),
        s.get("subsidy_rate", ""),
        s.get("start_date", ""),
        s.get("deadline", ""),
        s.get("region", ""),
        s.get("industry", ""),
        s.get("use_purpose", ""),
        s.get("target_employees", ""),
        s["source"],
        s.get("source_id") or None,
        s.get("source_url", ""),
        s.get("fetched_at", datetime.now().isoformat()),
    ))
    
    # 挿入/操作された行の ID を取得
    subsidy_id = cursor.lastrowid
    
    # 変更を確定して接続を閉じる
    conn.commit()
    conn.close()
    
    return subsidy_id


def get_all_subsidies() ->  list[dict]:
    """データベースに保存されているすべての補助金データを取得する
    Returns:
        list[dict]: 各行を辞書化した補助金データのリスト
    """
    conn = get_connection()
    rows = conn.execute("SELECT * FROM subsidies").fetchall()
    conn.close()
    return [dict(r) for r in rows]