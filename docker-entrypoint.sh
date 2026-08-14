#!/bin/sh
# Ensure the figures volume directory is writable by appuser.
# Named Docker volumes are created with root ownership; this script
# runs as root briefly before exec-ing the actual process as appuser.
mkdir -p /data/figures
chown -R appuser:appgroup /data/figures 2>/dev/null || true
exec gosu appuser "$@"
