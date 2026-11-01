#!/bin/sh
# The image against a root-owned ./data, as Docker creates a missing bind mount: `nestor init`
# writes into it as the nestor user (uid 1000), and `--user` runs the command as given.
# Needs a Docker host whose bind mounts keep Linux ownership, as on Linux and in CI: Docker Desktop
# and OrbStack share macOS folders under their own rules, where every file reads as root's.
# Usage: tests/docker/data-ownership.sh [image]  (builds the image from the repository when omitted)
set -eu

image=${1:-}
if [ -z "$image" ]; then
	image=nestor:data-ownership
	docker build --quiet --tag "$image" "$(dirname "$0")/../.." >/dev/null
fi
work=$(mktemp -d)
data="$work/data"
cleanup() {
	docker run --rm --volume "$work:/work" --entrypoint rm "$image" -rf /work/data
	rm -rf "$work"
}
trap cleanup EXIT

fail() {
	echo "FAIL: $*" >&2
	exit 1
}

# What Docker does with a missing bind-mounted folder: it creates it, owned by root.
docker run --rm --volume "$work:/work" --entrypoint sh "$image" -c 'mkdir /work/data && chown 0:0 /work/data'
owner() { docker run --rm --volume "$data:/data" --entrypoint stat "$image" -c %u "$1"; }
[ "$(owner /data)" = 0 ] || fail "the folder should start owned by root"

printf 'Nestor\nAlex\nalex\nten characters\nten characters\n' |
	docker run --rm --interactive --volume "$data:/data" "$image" init
[ "$(owner /data)" = 1000 ] || fail "/data should belong to nestor"
[ "$(owner /data/nestor.yaml)" = 1000 ] || fail "nestor init should have written nestor.yaml as nestor"
[ "$(owner /data/.env)" = 1000 ] || fail "nestor init should have written .env as nestor"

uid=$(docker run --rm --volume "$data:/data" --entrypoint docker-entrypoint.sh "$image" id -u)
[ "$uid" = 1000 ] || fail "the command should run as uid 1000, ran as $uid"
home=$(docker run --rm --volume "$data:/data" --entrypoint docker-entrypoint.sh "$image" sh -c 'echo "$HOME"')
[ "$home" = /home/nestor ] || fail "HOME should be nestor's, is $home"

uid=$(docker run --rm --user 1234:1234 --volume "$data:/data" --entrypoint docker-entrypoint.sh "$image" id -u)
[ "$uid" = 1234 ] || fail "--user 1234 should run as 1234, ran as $uid"
[ "$(owner /data)" = 1000 ] || fail "--user should leave /data as it is"

echo "ok: a root-owned /data is given to nestor, which writes in it as uid 1000; --user runs as given"
