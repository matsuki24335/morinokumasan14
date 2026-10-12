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

-- なかの追記
-- knowledgeテーブル（営業が蓄積する「補助金の活用事例・提案ナレッジ」）
-- 方針: 補助金側にある情報は持たず、subsidy_id で参照する（正規化）
CREATE TABLE IF NOT EXISTS knowledge (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,

    -- どの補助金の事例か
    subsidy_id       INTEGER NOT NULL,    --subsidyのidを軸とするための紐づけ            

    -- 事例側の情報（その店・その事例にしかないもの）
    usage_detail     TEXT NOT NULL,       -- 細かい用途（例：モバイルオーダー導入）
    received_amount  INTEGER DEFAULT 0,   -- 実際に受け取った金額(円。不明は0）
    shop_category    TEXT,                -- 店舗カテゴリ（居酒屋・カフェ等）
    shop_area        TEXT,                -- 事例の店がある場所
    proposal_point   TEXT,                -- 営業提案のポイント／成功・失敗の学び
    author           TEXT,                -- 記入した営業担当
-- 追加項目（ここから）
    owner_words      TEXT,                -- オーナーの元の言葉（相談内容）
    caution          TEXT,                -- 注意点・つまずき
    difficulty       TEXT,                -- 申請の難しさ（易／中／難）
    total_cost       INTEGER DEFAULT 0,   -- 自己負担額（総事業費、円。不明は0）
-- 追加項目（ここまで）

    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- subsidiesからの外部キー取得
    FOREIGN KEY (subsidy_id) REFERENCES subsidies(id)
);

-- 「この補助金のナレッジをください」を速くするための索引
CREATE INDEX IF NOT EXISTS idx_knowledge_subsidy_id ON knowledge(subsidy_id);

-- なかの追記
-- Favoriteテーブル
CREATE TABLE IF NOT EXISTS favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    knowledge_id INTEGER NOT NULL,
    user_name TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (knowledge_id) REFERENCES knowledge(id),
    UNIQUE(knowledge_id, user_name)
);