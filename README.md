# Skills Gap Analyzer

## Overview

Skills Gap Analyzer is a data-driven project that helps identify the gap between an individual's current skills and the skills demanded by the job market in Data, AI, and Python-related roles.

The project is developed incrementally over multiple weeks. This repository currently contains:

- **Week 1 — Data Input & Processing Component**, which focuses on building a local ETL pipeline to collect, clean, validate, store, and profile job listing data.
- **Week 2 — AI Analyzer Component**, which builds on Week 1's cleaned data to tag job listings with extracted tech stacks and detect skill gaps between a resume and the job market.
- **Week 3 — System Integration & Application**, which wraps the Week 2 logic in a full-stack, containerized chat application — a frontend and backend service, each in its own Docker container, orchestrated together with Docker Compose.

📌 The Week 1, Week 2, and Week 3 task details are provided below. ⬇️

---

## Core Concepts

This project applies several data engineering concepts:

* Data Ingestion
* Data Cleaning & Processing
* Data Validation
* Data Structuring
* Data Storage
* Data Profiling
* Orchestration
* Idempotency
* Medallion Architecture

---

## General Instructions

- All git commit messages must follow Conventional Commits v1.0.0
- Format all Python code with `ruff` version **0.15.***
- Ensure you are running python version **3.14**.*
- All packages are allowed, but unused packages must be removed from `pyproject.toml`, with the exception of OS-specific packages of course.
- Ensure all packages are pinned to exact versions to prevent breaking changes.
- Make sure your program and scripts support at least Linux/macOS and Windows. Platform independence will be checked; any platform-dependent code or scripts will be considered incomplete.

---

# Week 1 : Data Input & Processing Component

## Objective

The objective of Week 1 is to build a robust local data engineering pipeline that extracts raw job listing data from MHTML files, transforms it into structured and validated data, stores it in a relational database, and performs data quality checks.

➡️ [Click here to view Week 1](week_1/README.md)

---

# Week 2 : AI Analyzer Component

## Objective

The objective of Week 2 is to build the AI component of the skill gap detection pipeline on top of the cleaned data from Week 1. It tags each job listing in the database with an extracted tech stack using an LLM-backed pipeline (with a regex fast path to cut unnecessary model calls), then deterministically compares a candidate's resume against the tagged job market data to surface missing skills.

➡️ [Click here to view Week 2](week_2/README.md)

---

# Week 3 : System Integration & Application

## Objective

The objective of Week 3 is to take the Week 2 skill-gap analysis logic and wrap it in a full-stack, containerized chat application. A FastAPI frontend serves a chat interface where a user can paste resume text or upload a PDF resume (with text extracted entirely client-side via `pdf.js`); a separate FastAPI backend exposes a `/chat` endpoint that runs the Week 2 analysis against a real jobs database and generates a natural-language reply via an LLM. Each service has its own `Dockerfile` and the two are orchestrated together with Docker Compose on a shared network, with the database mounted directly into the backend container.

Beyond the mandatory frontend/backend containerization, this week also includes two bonus features: a switchable second LLM provider (Ollama, alongside Gemini) for conversational replies, and Docker secrets for keeping the Gemini API key out of plain environment variables.

➡️ [Click here to view Week 3](week_3/README.md)

---

# Author

**Mohandass**