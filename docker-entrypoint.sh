#!/bin/sh
# Starts as root only to make sure the database directory (usually a mounted
# volume, which Docker creates owned by root) is writable by appuser, then
# drops privileges and runs the bot as appuser.
set -e

if [ "$(id -u)" = "0" ]; then
    db_dir="$(dirname "${SONGKISSER_DB:-/data/songkisser.db}")"
    mkdir -p "$db_dir"
    chown appuser:appuser "$db_dir"
    exec setpriv --reuid=appuser --regid=appuser --init-groups "$@"
fi

exec "$@"
