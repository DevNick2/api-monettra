-- Extensões necessárias para o projeto Monettra
-- Este arquivo é executado UMA ÚNICA VEZ na inicialização do container PostgreSQL.
-- As tabelas são criadas e gerenciadas pelo Alembic (db/alembic/).

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;
