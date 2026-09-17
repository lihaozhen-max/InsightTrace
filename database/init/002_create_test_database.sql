SELECT 'CREATE DATABASE insighttrace_test OWNER insighttrace'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'insighttrace_test')\gexec
