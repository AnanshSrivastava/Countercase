-- Runs once on first start of the db volume.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE DATABASE hindsight;
\connect hindsight
CREATE EXTENSION IF NOT EXISTS vector;
