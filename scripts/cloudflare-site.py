#!/usr/bin/env python3
"""Keep Arcade's Cloudflare Pages project and arcade.waozi.xyz in place.

`prepare` creates the `arcade` Pages project when it is missing, before the
first deployment. `connect` adds arcade.waozi.xyz to the project and points
its DNS at the project. Both are safe to repeat on every deployment. They read
CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID and never print the token.
"""
import json
import os
import sys
import urllib.error
import urllib.request

PROJECT = 'arcade'
DOMAIN = 'arcade.waozi.xyz'
ZONE = 'waozi.xyz'


def api(method, path, body=None):
    request = urllib.request.Request('https://api.cloudflare.com/client/v4' + path, method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Authorization': 'Bearer ' + os.environ['CLOUDFLARE_API_TOKEN'], 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b'{}')


def result(method, path, body=None):
    status, data = api(method, path, body)
    if not data.get('success'):
        raise SystemExit(f'Cloudflare {method} {path} failed ({status}): {data.get("errors")}')
    return data['result']


def prepare(account):
    status, data = api('GET', f'/accounts/{account}/pages/projects/{PROJECT}')
    if data.get('success'):
        print(f'Pages project {PROJECT} exists.')
        return
    if status != 404:
        raise SystemExit(f'Could not read Pages project {PROJECT} ({status}): {data.get("errors")}')
    result('POST', f'/accounts/{account}/pages/projects', {'name': PROJECT, 'production_branch': 'master'})
    print(f'Created Pages project {PROJECT}.')


def connect(account):
    project = result('GET', f'/accounts/{account}/pages/projects/{PROJECT}')
    domains = result('GET', f'/accounts/{account}/pages/projects/{PROJECT}/domains')
    if not any(domain['name'] == DOMAIN for domain in domains):
        result('POST', f'/accounts/{account}/pages/projects/{PROJECT}/domains', {'name': DOMAIN})
        print(f'Added {DOMAIN} to Pages project {PROJECT}.')
    zones = result('GET', f'/zones?name={ZONE}')
    if len(zones) != 1:
        raise SystemExit(f'Expected one {ZONE} zone, found {len(zones)}')
    zone = zones[0]['id']
    records = result('GET', f'/zones/{zone}/dns_records?name={DOMAIN}')
    if not records:
        result('POST', f'/zones/{zone}/dns_records',
               {'type': 'CNAME', 'name': DOMAIN, 'content': project['subdomain'], 'proxied': True, 'ttl': 1})
        print(f'Pointed {DOMAIN} at {project["subdomain"]}.')
    elif not (len(records) == 1 and records[0]['type'] == 'CNAME' and records[0]['content'] == project['subdomain']):
        # Never overwrite a record someone else made.
        raise SystemExit(f'{DOMAIN} already has DNS records that do not point at {project["subdomain"]}')
    print(f'{DOMAIN} serves Pages project {PROJECT}.')


if __name__ == '__main__':
    if len(sys.argv) != 2 or sys.argv[1] not in {'prepare', 'connect'}:
        raise SystemExit('Usage: cloudflare-site.py prepare|connect')
    account = os.environ['CLOUDFLARE_ACCOUNT_ID']
    {'prepare': prepare, 'connect': connect}[sys.argv[1]](account)
