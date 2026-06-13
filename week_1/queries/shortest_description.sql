SELECT source_id, job_title, LENGTH(description)
FROM jobs
ORDER BY LENGTH(description) ASC
LIMIT 1