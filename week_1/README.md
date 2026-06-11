# Week 1 : Data Component

# Data Input & Processing Component

## Project Description

### Goal

The goal of this project is to build a local ETL (Extract, Transform, Load) pipeline that processes job listing data using a Medallion Architecture approach. The pipeline extracts raw job listing information from MHTML files, transforms the data into validated JSON records, loads the cleaned data into a SQLite database, and generates a data quality report for validation and analysis.

### Architecture Overview

```text
0_source (.mhtml)
        ↓
1_bronze (.html)
        ↓
2_silver (.json)
        ↓
3_gold (SQLite Database)
        ↓
Data Profiling
```

### Project Structure

```text
project-root/
│
├── data/
│   ├── 0_source/
│   ├── 1_bronze/
│   ├── 2_silver/
│   └── 3_gold/
│
├── src/
│   ├── ingestor.py
│   ├── processor.py
│   ├── loader.py
│   └── profiler.py
│
├── main.py
├── pyproject.toml
├── uv.lock
└── README.md
```

---

# Setup Instructions

## Prerequisites

Before running this project, ensure the following are installed:

- Python 3.14 or later
- Git
- UV Package Manager
- VS Code (recommended)


## Project Setup

### 1. Create Python Version File

Create a `.python-version` file in the project root and add:

```text
3.14
```

### 2. Install uv

Follow the official installation guide for `uv`.

### 3. Initialize the Project

Install Python, initialize the project, and create a virtual environment:

```bash
uv python install
uv init
uv venv
```

Activate the virtual environment:

#### Windows

```bash
.venv\Scripts\activate
```

#### Linux / macOS

```bash
source .venv/bin/activate
```

### 4. Install Dependencies

Install the required packages:

```bash
uv add bs4 ruff pydantic
```

This will install:

- BeautifulSoup (`bs4`)
- Ruff (linter and formatter)
- Pydantic (data validation)

### 5. Configure .gitignore

Create a `.gitignore` file in the project root and add:

```text
data/
src/__pycache__/
.ruff_cache/
.venv/
```

### 6. Synchronize Dependencies

After cloning the project, install all dependencies:

```bash
uv sync
```

---

# Usage

## Bronze Layer - Extract HTML from MHTML

Command:

```bash
python main.py ingest
```

Input:

```text
data/0_source/*.mhtml
```

Output:

```text
data/1_bronze/*.html
```

Purpose:

- Read MHTML files
- Extract HTML content
- Store extracted HTML in the Bronze layer

---

## Silver Layer - Clean and Structure Data

Command:

```bash
python main.py process
```

Input:

```text
data/1_bronze/*.html
```

Output:

```text
data/2_silver/*.json
```

Purpose:

- Parse HTML using BeautifulSoup
- Extract:
  - source_id
  - job_title
  - company
  - description
- Validate records using Pydantic
- Save valid records as JSON

Example JSON:

```json
{
  "source_id": "12345678",
  "job_title": "Data Analyst",
  "company": "ABC Company",
  "description": "Job description..."
}
```

---

## Gold Layer - Load into SQLite

Command:

```bash
python main.py load
```

Input:

```text
data/2_silver/*.json
```

Output:

```text
data/3_gold/jobs.db
```

Purpose:

- Create SQLite database
- Create jobs table
- Insert validated records
- Prevent duplicate records using INSERT OR IGNORE

---

## Data Profiling

Command:

```bash
python main.py profile
```

Purpose:

Generate a data quality report including:

- Total Records
- Missing Values
- Average Description Length
- Shortest Description
- Longest Description

Example Output:

```text
🔍 DATA QUALITY REPORT

Total Records: 84

Missing Values
job_title: 0
company: 0
description: 0

Average Description Length: 2654 chars

Shortest Description:
source_id: 91647393
job_title: Software Engineer

Longest Description:
source_id: 91731564
job_title: Automation Engineer
```

---

## Run Complete Pipeline

Command:

```bash
python main.py all
```

Execution Order:

```text
ingest
 ↓
process
 ↓
load
 ↓
profile
```

---

## Available Commands

```bash
python main.py ingest
python main.py process
python main.py load
python main.py profile
python main.py all
```

---

# Technical Reflections

## Day 1: The Extractor (Medallion & Lakehouses)

### Question

Why is it useful to keep the original raw HTML files instead of directly inserting processed data into the database? What problems become easier to debug or recover from?

### Answer

Keeping the original raw HTML files in the Bronze layer provides a reliable source of truth. If extraction logic, validation rules, or business requirements change, the pipeline can be rerun without recollecting the data. This approach also simplifies debugging because processed outputs can be compared against the original HTML files to identify issues. Additionally, retaining raw files makes recovery easier when processing errors, corrupted outputs, or unexpected failures occur in downstream layers.

---

## Day 2: Treatment Plant (ETL vs ELT & Scale)

### Question

Why do cloud systems prefer loading raw data first before cleaning it (ELT)? What problems happen when processing files sequentially, and how does distributed processing help?

### Answer

Loading raw data first provides flexibility because transformation logic can be modified or improved later without re-ingesting the source data. In this project, an ETL approach was used where HTML files were cleaned, validated, and transformed before loading into the database. While sequential processing is suitable for small datasets, it becomes inefficient as data volume increases. Distributed processing frameworks such as Apache Spark improve scalability by processing multiple files simultaneously across multiple workers, significantly reducing execution time.

---

## Day 3: The Blueprint & The Vault (Storage & Contracts)

### Question

What should happen if an important field like `job_title` disappears? Why fail early instead of silently inserting nulls into DB? How does `INSERT OR IGNORE` help prevent duplicate records?

### Answer

If critical fields such as `job_title`, `company`, or `description` are missing, the record should be rejected during the validation stage. Failing early prevents incomplete or inaccurate data from entering the database and affecting analytics, reporting, or downstream processes. In this project, only validated records are stored in the Silver layer and loaded into SQLite. The use of `INSERT OR IGNORE` ensures idempotency by preventing duplicate records from being inserted when the pipeline is executed multiple times.

---

## Day 4: The QA Inspector & Orchestrator (Orchestration & DAGs)

### Question

What happens if `processor.py` crashes halfway? How are automated orchestration tools more reliable than manual retries with Python scripts?

### Answer

If `processor.py` crashes midway, only a subset of files may be processed, resulting in an incomplete pipeline execution. In this project, `main.py` acts as a simple orchestrator that allows each stage to be executed independently or through the `all` command. However, enterprise orchestration tools such as Apache Airflow provide additional capabilities including scheduling, dependency management, automatic retries, monitoring, alerting, and execution tracking. These features improve reliability and reduce manual intervention when failures occur.

---




