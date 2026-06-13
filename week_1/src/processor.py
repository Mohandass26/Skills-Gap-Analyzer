from pathlib import Path
import json
import re
from bs4 import BeautifulSoup
from pydantic import BaseModel, ValidationError


class JobListing(BaseModel):
    source_id: str
    job_title: str
    company: str
    description: str


def clean_text(element):
    if element is None:
        return ""

    return element.get_text(separator=" ", strip=True)


def extract_source_id(soup):
    og_url = soup.find("meta", property="og:url")

    if og_url and og_url.get("content"):
        url = og_url.get("content").rstrip("/")
        return url.split("/")[-1]

    return ""


def extract_job_title(soup):
    title_element = soup.find(attrs={"data-automation": "job-detail-title"})

    if title_element:
        return clean_text(title_element)

    h1 = soup.find("h1")
    return clean_text(h1)


def extract_company(soup):
    company_element = soup.find(attrs={"data-automation": "advertiser-name"})

    if company_element:
        return clean_text(company_element)

    return ""


def extract_description(soup):
    description_element = soup.find(attrs={"data-automation": "jobAdDetails"})

    if description_element:
        return clean_text(description_element)

    return ""


def process_all_html(input_dir, output_dir):
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    output_path.mkdir(parents=True, exist_ok=True)

    print("🥈 Silver:...")

    if not input_path.exists():
        print("⚠️ Source directory not found.")
        print("\n📊 Silver Summary:")
        print("Total: 0 | Processed: 0 | Skipped: 0")
        return

    files = list(input_path.glob("*.html"))

    total = len(files)
    processed = 0
    skipped = 0

    for file in files:
        try:
            html_content = file.read_text(encoding="utf-8")

            soup = BeautifulSoup(html_content, "html.parser")

            data = {
                "source_id": extract_source_id(soup),
                "job_title": extract_job_title(soup),
                "company": extract_company(soup),
                "description": extract_description(soup),
            }

            missing_fields = [
                field for field, value in data.items()
                if not value
            ]

            if missing_fields:
                for field in missing_fields:
                    print(f"⚠️  Missing {field} in: {file.name}")

                skipped += 1
                continue

            job_listing = JobListing(**data)

            output_file = output_path / f"{file.stem}.json"

            with open(output_file, "w", encoding="utf-8") as out:
                json.dump(
                    job_listing.model_dump(),
                    out,
                    ensure_ascii=False,
                    indent=2
                )

            print(f"✅ Processed: {file.name}")
            processed += 1

        except ValidationError as e:
            print(f"❌ Validation failed in: {file.name} - {e}")
            skipped += 1

        except Exception as e:
            print(f"❌ Failed: {file.name} - {e}")
            skipped += 1

    print("\n📊 Silver Summary:")
    print(f"Total: {total} | Processed: {processed} | Skipped: {skipped}")