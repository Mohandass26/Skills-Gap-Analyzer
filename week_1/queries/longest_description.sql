SELECT source_id, job_title, LENGTH(description)
FROM jobs
ORDER BY LENGTH(description) DESC
LIMIT 1