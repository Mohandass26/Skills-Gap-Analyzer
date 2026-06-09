from pathlib import Path
from email import policy
from email.parser import BytesParser


def ingest_all_mhtml(input_dir, output_dir):
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    output_path.mkdir(parents=True, exist_ok=True)

    print("🥉 Bronze:...")

    if not input_path.exists():
        print("⚠️ Source directory not found.")
        print("\n📊 Bronze Summary:")
        print("Total: 0 | Extracted: 0 | Failed: 0")
        return

    files = list(input_path.glob("*.mhtml"))

    total = len(files)
    extracted = 0
    failed = 0

    for file in files:
        try:
            with open(file, "rb") as f:
                msg = BytesParser(policy=policy.default).parse(f)

            html_content = None

            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/html":
                        html_content = part.get_content()
                        break
            else:
                if msg.get_content_type() == "text/html":
                    html_content = msg.get_content()

            if not html_content:
                print(f"⚠️ No HTML content found in: {file.name}")
                failed += 1
                continue

            output_file = output_path / f"{file.stem}.html"

            with open(output_file, "w", encoding="utf-8") as out:
                out.write(html_content)

            print(f"✅ Extracted: {file.name}")
            extracted += 1

        except Exception as e:
            print(f"❌ Failed: {file.name} - {e}")
            failed += 1

    print("\n📊 Bronze Summary:")
    print(f"Total: {total} | Extracted: {extracted} | Failed: {failed}")