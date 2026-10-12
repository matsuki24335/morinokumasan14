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
    conn.execute("PRAGMA foreign_keys = ON")   # なかの追記
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

#なかの追記
def insert_knowledge(k: dict) -> int:
    """ナレッジ（活用事例）を1件登録する

    Args:
        k (dict): subsidy_id と usage_detail は必須。ほかは省略可。
    Returns:
        int: 登録されたナレッジの id
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO knowledge
            (subsidy_id, usage_detail, received_amount,
            shop_category, shop_area, proposal_point,
            author, owner_words, caution, difficulty, total_cost)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        k["subsidy_id"],
        k["usage_detail"],
        k.get("received_amount", 0),
        k.get("shop_category", ""),   # shop_category
        k.get("shop_area", ""),       # shop_area
        k.get("proposal_point", ""),  # proposal_point
        k.get("author", ""),          # author
        k.get("owner_words", ""),     # owner_words
        k.get("caution", ""),         # caution
        k.get("difficulty", ""),      # difficulty
        k.get("total_cost", 0),      # total_cost
    ))

    knowledge_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return knowledge_id

#なかの追記
def get_knowledge_by_subsidy(subsidy_id: int) -> list[dict]:
    """指定した補助金に紐づくナレッジを、新しい順に返す

    Args:
        subsidy_id (int): subsidies.id
    Returns:
        list[dict]: ナレッジのリスト（無ければ空リスト）
    """
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM knowledge WHERE subsidy_id = ? ORDER BY created_at DESC",
        (subsidy_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

#なかの追記
#事例一覧タブで用いる関数。
def get_all_knowledge() -> list[dict]:
    """全ナレッジを、補助金名つきで新しい順に返す（事例一覧タブ用）

    Returns:
        list[dict]: ナレッジの全列 + subsidy_title（補助金名）
    """
    conn = get_connection()
    rows = conn.execute("""
        SELECT k.*, s.title AS subsidy_title
        FROM knowledge k
        JOIN subsidies s ON k.subsidy_id = s.id
        ORDER BY k.created_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


#なかの追記
#お気に入り、を押すための関数
def add_favorite(knowledge_id, user_name):
    """お気に入りを登録する。同じ人が同じ事例を2回押したら False を返す"""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO favorites (knowledge_id, user_name) VALUES (?, ?)",
            (knowledge_id, user_name),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

#なかの追記
#お気に入りの数を数える
def get_favorite_counts():
    """事例ごとのお気に入り数を {knowledge_id: 件数} の辞書で返す"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT knowledge_id, COUNT(*) AS cnt FROM favorites GROUP BY knowledge_id"
    ).fetchall()
    conn.close()
    return {r["knowledge_id"]: r["cnt"] for r in rows}