#!/bin/bash

# Export PGPASSWORD to avoid password prompt
export PGPASSWORD=$POSTGRES_PASSWORD

# Wait for Postgres to be ready
echo "Waiting for Postgres at $DB_HOST..."
until psql -h "$DB_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\q'; do
  >&2 echo "Postgres is unavailable - sleeping"
  sleep 2
done
echo "Postgres is up!"

# Check if the 'version' table exists (indicates DB is initialized)
TABLE_EXISTS=$(psql -h "$DB_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT to_regclass('public.version');")

if [ "$TABLE_EXISTS" == "" ]; then
    echo "Database is empty. Initializing Kamailio Schema..."
    
    # Path where Kamailio stores default SQL schemas
    SQL_DIR="/usr/share/kamailio/postgres"

    psql -h "$DB_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f $SQL_DIR/standard-create.sql
    psql -h "$DB_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f $SQL_DIR/usrloc-create.sql
    psql -h "$DB_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f $SQL_DIR/auth-create.sql
    
    echo "Schema Initialization Complete."
else
    echo "Database already initialized."
fi

# Start Kamailio
exec /usr/sbin/kamailio -DD -E -f /etc/kamailio/kamailio.cfg
