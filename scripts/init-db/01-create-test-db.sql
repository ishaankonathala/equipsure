-- Creates the equipsure_test database on first container start (new volume only).
SELECT 'CREATE DATABASE equipsure_test' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'equipsure_test')\gexec
