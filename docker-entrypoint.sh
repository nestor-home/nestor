#!/bin/sh
# Starts as root only to give /data to the nestor user, then runs the command as nestor.
# Docker creates a missing bind-mounted folder owned by root, where nestor could not write.
# Only the folder itself changes hands: whatever is inside is either Nestor's already or was
# put there by the person, who keeps it. Started with --user, the command runs as given.
set -eu

if [ "$(id -u)" = 0 ]; then
	if [ "$(stat -c %u /data)" != "$(id -u nestor)" ]; then
		chown nestor:nestor /data
	fi
	export HOME=/home/nestor
	exec setpriv --reuid=nestor --regid=nestor --init-groups -- "$@"
fi
exec "$@"
