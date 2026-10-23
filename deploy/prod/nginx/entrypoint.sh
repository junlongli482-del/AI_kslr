#!/bin/sh
set -eu
: "${AUTH_USER1:?set AUTH_USER1}"
: "${AUTH_PASS1:?set AUTH_PASS1}"
: "${AUTH_USER2:?set AUTH_USER2}"
: "${AUTH_PASS2:?set AUTH_PASS2}"

{
    echo "${AUTH_USER1}:$(openssl passwd -apr1 "${AUTH_PASS1}")"
    echo "${AUTH_USER2}:$(openssl passwd -apr1 "${AUTH_PASS2}")"
} > /etc/nginx/.htpasswd

exec nginx -g 'daemon off;'
