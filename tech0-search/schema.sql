-- schema.sql
-- 補補助金逆引きアプリ MVP データベース設計

-- subsidiesテーブル（メイン）
CREATE TABLE IF NOT EXISTS subsidies (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,

    -- 制度の中身
    title         TEXT NOT NULL,       -- 制度名
    description   TEXT,                -- 概要
    max_amount    INTEGER DEFAULT 0,   -- 上限額（円。不明は0）
    subsidy_rate  TEXT,                -- 補助率（"1/2"など文字列で。表記ばらばらのため）
    start_date    TEXT,                -- 申請開始日
    deadline      TEXT,                -- 申請締切

    -- 対象の絞り込み条件
    region        TEXT,                -- 対象地域（"全国" "東京都" "豊島区"）
    industry      TEXT,                -- 対象業種
    use_purpose   TEXT,                -- 利用目的タグ
    target_employees TEXT,             -- 対象従業員数

    -- 出どころ管理
    source        TEXT NOT NULL,       -- "jgrants" or "municipal_pdf"
    source_id     TEXT,                -- 情報源側の制度ID（PDF由来は空でOK）
    source_url    TEXT,                -- 公式ページURL
    fetched_at    DATETIME,            -- 取得日時

    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (source, source_id)
);

-- インデックス（よく絞り込む項目の検索を速くする）
CREATE INDEX IF NOT EXISTS idx_subsidies_region      ON subsidies(region);
CREATE INDEX IF NOT EXISTS idx_subsidies_deadline    ON subsidies(deadline);
CREATE INDEX IF NOT EXISTS idx_subsidies_use_purpose ON subsidies(use_purpose);

-- ※ search_logs（検索履歴）は、必要性があれば将来追加する