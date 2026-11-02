-- PostgreSQL High-Concurrency Tuning (Run inside kbl_postgres when scaling to 1,000+ users)
ALTER SYSTEM SET max_connections = '200';
ALTER SYSTEM SET shared_buffers = '128MB';
ALTER SYSTEM SET effective_cache_size = '384MB';
ALTER SYSTEM SET work_mem = '4MB';
-- Requires container restart: sudo docker restart kbl_postgres
