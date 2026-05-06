-- Enable PostGIS and required extensions on database init
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- fast text search
CREATE EXTENSION IF NOT EXISTS btree_gin;
