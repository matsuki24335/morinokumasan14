# =============================================================
# pdf_ingest.py — 補助金逆引きアプリ MVP
# PDFから制度を読み取り
# register_pdf_subsidyにて人が確認してDBへ登録
# ============================================================= 

from pathlib import Path
import pdfplumber

# このPythonファイルがある場所を基準に、PDFと出力先を決める
BASE_DIR = Path(__file__).resolve().parent
PDF_PATH = BASE_DIR / "data" / "input" / "20260415124004.pdf"
TEXT_PATH = BASE_DIR / "data" / "output" / "toshima_2026_extracted.txt"


def extract_pdf_text(pdf_path: Path) -> str:
    """PDFの全ページから文字を取り出して、ひとつの文章にまとめる"""
    page_texts = []

    with pdfplumber.open(pdf_path) as pdf:
        print(f"ページ数: {len(pdf.pages)}")

        for page_number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            page_texts.append(text)
            print(f"{page_number}ページ目: {len(text)}文字")

    return "\n\n".join(page_texts)


def main():
    if not PDF_PATH.exists():
        print("PDFが見つかりません。保存場所とファイル名を確認してください。")
        print(f"探している場所: {PDF_PATH}")
        return

    text = extract_pdf_text(PDF_PATH)

    TEXT_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEXT_PATH.write_text(text, encoding="utf-8")

    print(f"\n抽出した文字数: {len(text)}")
    print(f"抽出テキストの保存先: {TEXT_PATH}")

    print("\n--- 抽出テキストの先頭 ---")
    print(text[:1200])


if __name__ == "__main__":
    main()
